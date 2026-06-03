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
- Favor precision over recall: when uncertain, reject; do not guess; do not infer unsupported concepts.
- Do NOT treat loosely related concepts as equivalent unless explicitly supported by the catalog.

Reject examples (unless explicitly defined in the catalog):
- product category mapped to subscription plan
- churn risk mapped to churn
- paying customers mapped to subscriptions
- customer satisfaction mapped to user activity

Accept visualization and analytics phrasing when underlying business concepts exist in the catalog:
- chart, graph, line chart, bar chart, histogram, scatter plot, visualize, trend
- time grouping (monthly, quarterly), aggregation, comparison, breakdown, segmentation

Classification outcomes:
- answerable=true, kind="answerable": every business concept maps to the catalog or is generic analytics phrasing.
- answerable=false, kind="concept_mismatch": the question references concepts absent from the catalog.
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
