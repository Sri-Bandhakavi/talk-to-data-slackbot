from __future__ import annotations

import json
import re
from pathlib import Path

from pandasai.core.prompts.base import BasePrompt
from pandasai_litellm import LiteLLM

from talk_to_data_slackbot.config import Settings, get_settings
from talk_to_data_slackbot.pandas_ai.answerability import (
    AnswerabilityAssessment,
    RejectionKind,
)
from talk_to_data_slackbot.pandas_ai.concept_lexicon import build_concept_lexicon
from talk_to_data_slackbot.pandas_ai.llm import LLMConfigurationError, build_answerability_llm
from talk_to_data_slackbot.pandas_ai.semantic_loader import (
    SemanticModelDefinition,
    load_semantic_models,
)

_VALID_KINDS = frozenset(kind.value for kind in RejectionKind)
_JSON_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)
_CATALOG_DESCRIPTION_LIMIT = 500
_LEXICON_TERM_SAMPLE_LIMIT = 50

_CLASSIFIER_POLICY = """You are an answerability classifier for a Slack analytics bot.

Your task is to decide whether a user question can be answered using ONLY the semantic catalog below.

Rules:
- Do NOT answer the user question.
- Do NOT generate SQL or analytics code.
- Determine answerability only.
- Ground every decision in the semantic catalog. Do not use knowledge outside the catalog.

How to classify (follow in order):
1. Identify core business concepts in the question. Ignore generic analytics phrasing (chart, trend, total, comparison, breakdown, ranking, time grouping, superlatives).
2. For each core concept, search the catalog for support in column names, [alias: ...] tags, column descriptions, dataset descriptions (including documented business questions and business rules), relationships, and join context.
3. A concept is supported when catalog metadata explicitly documents it—not when you infer an unstated qualifier or substitute a related but undocumented term.
4. For multi-dataset questions, check whether relationships in the catalog connect the required datasets. If yes, treat the combined question as supported when each concept maps to those datasets.
5. Reject only if a core business concept remains unsupported after steps 1–4.

How to interpret business language:
- Users may phrase questions in executive or informal language rather than exact catalog terms.
- Paraphrase is allowed for nouns, metrics, and dimensions when [alias: ...] tags or descriptions in the catalog document the mapping.
- Do not paraphrase status or scope qualifiers (words that narrow who/what qualifies) unless the catalog explicitly defines that qualifier in a column, alias, description, or business rule.
- Superlatives and comparisons are generic analytics phrasing when a supported metric and breakdown dimension exist in the catalog.

Documented analytics vs predictive concepts:
- Accept descriptive or historical analytics when catalog descriptions, columns, or business rules document the metric or lifecycle concept (including churn, retention, or lifecycle analysis defined in dataset descriptions).
- Reject predictive or scoring concepts—risk, likelihood, propensity, forecast, or prediction—when those specific concepts are not defined in the catalog.
- Do not treat a documented lifecycle metric as a predictive score, and do not treat a predictive score as supported merely because a related lifecycle metric exists in the catalog.

Precision and recall:
- Accept when every core business concept has catalog metadata support, including through aliases, descriptions, or relationship-supported multi-table context.
- Reject genuinely unsupported concepts and out-of-domain questions.
- Do not accept by attaching an unsupported qualifier to an otherwise supported entity or dimension.
- When uncertain whether a qualifier is catalog-supported, reject the qualifier (concept_mismatch).
- When a documented catalog concept clearly matches the question through metadata, accept even if the exact wording differs.

Reject (no reasonable catalog support):
- Concepts with no related column, alias, description, or dataset context in the catalog
- Product categories, satisfaction scores, or sentiment metrics not defined in the catalog
- Predictive risk, likelihood, propensity, or forecast metrics not defined in the catalog
- Status or scope qualifiers not explicitly defined in the catalog, including when combined with otherwise supported entities or dimensions
- Trivia, puzzles, or general knowledge unrelated to business data

Reasoning boundaries (patterns, not vocabulary mappings):
- Accept pattern: each core concept maps to catalog metadata; multi-dataset questions use declared relationships; generic analytics phrasing wraps supported concepts.
- Reject pattern: a core concept has no catalog entry; a predictive score is requested without catalog definition; a qualifier narrows scope without catalog definition; unrelated business domains are introduced.

Accept visualization and analytics phrasing when underlying business concepts are catalog-supported:
- chart, graph, line chart, bar chart, histogram, scatter plot, visualize, trend
- time grouping (monthly, quarterly), aggregation, comparison, breakdown, segmentation, ranking, distribution

Classification outcomes:
- answerable=true, kind="answerable": every core business concept has reasonable catalog support, or only generic analytics phrasing remains unmatched.
- answerable=false, kind="concept_mismatch": a core business concept has no reasonable catalog support.
- answerable=false, kind="out_of_domain": trivia, puzzles, or general knowledge unrelated to business data.

Return JSON only with this schema (no markdown fences, no extra text):
{
  "answerable": boolean,
  "kind": "answerable" | "concept_mismatch" | "out_of_domain",
  "unmatched_concepts": ["string"],
  "reason": "string"
}
"""


class AnswerabilityClassifierError(Exception):
    """Raised when LLM answerability classification fails."""


class AnswerabilityClassifierPrompt(BasePrompt):
    """Single-message prompt for the answerability classifier."""

    template = "{{ prompt_text }}"


def build_semantic_catalog(models_dir: Path | None = None) -> str:
    """Serialize semantic models into a catalog string for the classifier."""
    models = load_semantic_models(models_dir)
    sections: list[str] = []

    for model in models.models:
        sections.append(_format_dataset(model))

    lexicon = build_concept_lexicon(models)
    sample_terms = sorted(lexicon.terms)[:_LEXICON_TERM_SAMPLE_LIMIT]
    if sample_terms:
        sections.append(
            "Known business terms (sample): " + ", ".join(sample_terms)
        )

    return "\n\n".join(sections)


def build_classifier_prompt(question: str, catalog: str) -> str:
    """Build the full classifier prompt text."""
    return (
        f"{_CLASSIFIER_POLICY}\n\n"
        f"Semantic catalog:\n{catalog}\n\n"
        f"Question: {question.strip()}"
    )


def parse_classifier_response(raw: str) -> dict[str, object]:
    """Parse and validate the classifier JSON response."""
    text = raw.strip()
    if not text:
        raise AnswerabilityClassifierError("Empty LLM response")

    fence_match = _JSON_FENCE_PATTERN.match(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnswerabilityClassifierError(
            f"Invalid JSON in classifier response: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise AnswerabilityClassifierError(
            "Classifier response must be a JSON object"
        )

    _validate_classifier_payload(payload)
    return payload


def map_to_assessment(
    question: str,
    payload: dict[str, object],
) -> AnswerabilityAssessment:
    """Map validated classifier JSON to AnswerabilityAssessment."""
    answerable = payload["answerable"]
    kind = RejectionKind(str(payload["kind"]))
    raw_unmatched = payload["unmatched_concepts"]
    reason = str(payload["reason"]).strip()

    unmatched = tuple(
        sorted(
            {
                str(item).strip().lower()
                for item in raw_unmatched  # type: ignore[union-attr]
                if str(item).strip()
            }
        )
    )

    return AnswerabilityAssessment(
        answerable=bool(answerable),
        kind=kind,
        question=question,
        unmatched_concepts=unmatched,
        reason=reason,
    )


def assess_with_llm_classifier(
    question: str,
    *,
    models_dir: Path | None = None,
    settings: Settings | None = None,
    llm: LiteLLM | None = None,
) -> AnswerabilityAssessment:
    """Classify answerability via LLM; raise AnswerabilityClassifierError on failure."""
    resolved = settings or get_settings()
    catalog = build_semantic_catalog(models_dir)
    prompt_text = build_classifier_prompt(question, catalog)

    active_llm = llm
    if active_llm is None:
        try:
            active_llm = build_answerability_llm(resolved)
        except LLMConfigurationError as exc:
            raise AnswerabilityClassifierError(str(exc)) from exc

    try:
        raw = active_llm.call(
            AnswerabilityClassifierPrompt(prompt_text=prompt_text)
        )
    except Exception as exc:
        raise AnswerabilityClassifierError(f"LLM call failed: {exc}") from exc

    payload = parse_classifier_response(raw)
    return map_to_assessment(question, payload)


def _format_dataset(model: SemanticModelDefinition) -> str:
    lines = [f"Dataset: {model.name}"]

    description = " ".join(model.description.split())
    if len(description) > _CATALOG_DESCRIPTION_LIMIT:
        description = description[:_CATALOG_DESCRIPTION_LIMIT] + "..."
    lines.append(f"Description: {description}")

    lines.append("Columns:")
    for column in model.columns:
        column_line = f"- {column.name} ({column.type}): {column.description}"
        if column.alias:
            column_line += f" [alias: {column.alias}]"
        if column.expression:
            column_line += f" [expression: {column.expression}]"
        lines.append(column_line)

    if model.relationships:
        lines.append("Relationships:")
        for relationship in model.relationships:
            lines.append(
                f"- {relationship.from_column} -> "
                f"{relationship.to.dataset}.{relationship.to.column}"
            )

    return "\n".join(lines)


def _validate_classifier_payload(payload: dict[str, object]) -> None:
    required_fields = ("answerable", "kind", "unmatched_concepts", "reason")
    for field in required_fields:
        if field not in payload:
            raise AnswerabilityClassifierError(
                f"Classifier response missing required field: {field}"
            )

    answerable = payload["answerable"]
    kind = payload["kind"]
    unmatched = payload["unmatched_concepts"]
    reason = payload["reason"]

    if not isinstance(answerable, bool):
        raise AnswerabilityClassifierError(
            "Classifier field 'answerable' must be a boolean"
        )

    if not isinstance(kind, str) or kind not in _VALID_KINDS:
        raise AnswerabilityClassifierError(
            f"Classifier field 'kind' must be one of: {sorted(_VALID_KINDS)}"
        )

    if not isinstance(unmatched, list) or not all(
        isinstance(item, str) for item in unmatched
    ):
        raise AnswerabilityClassifierError(
            "Classifier field 'unmatched_concepts' must be an array of strings"
        )

    if not isinstance(reason, str) or not reason.strip():
        raise AnswerabilityClassifierError(
            "Classifier field 'reason' must be a non-empty string"
        )

    if answerable and kind != RejectionKind.ANSWERABLE.value:
        raise AnswerabilityClassifierError(
            "Classifier response inconsistent: answerable=true requires kind='answerable'"
        )

    if not answerable and kind == RejectionKind.ANSWERABLE.value:
        raise AnswerabilityClassifierError(
            "Classifier response inconsistent: answerable=false requires kind!='answerable'"
        )


__all__ = [
    "AnswerabilityClassifierError",
    "AnswerabilityClassifierPrompt",
    "assess_with_llm_classifier",
    "build_classifier_prompt",
    "build_semantic_catalog",
    "map_to_assessment",
    "parse_classifier_response",
]
