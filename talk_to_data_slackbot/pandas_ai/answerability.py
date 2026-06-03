from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from talk_to_data_slackbot.pandas_ai.answerability_synonyms import apply_synonyms
from talk_to_data_slackbot.pandas_ai.answerability_vocabulary import (
    ANALYTICS_REQUEST_VOCABULARY,
)
from talk_to_data_slackbot.pandas_ai.concept_lexicon import (
    ConceptLexicon,
    build_concept_lexicon,
    clear_lexicon_cache,
    get_default_concept_lexicon,
)
from talk_to_data_slackbot.config import get_settings
from talk_to_data_slackbot.pandas_ai.semantic_loader import load_semantic_models

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "many",
        "me",
        "much",
        "my",
        "of",
        "on",
        "or",
        "our",
        "show",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "to",
        "us",
        "was",
        "we",
        "what",
        "when",
        "which",
        "who",
        "will",
        "with",
        "won",
        "would",
        "you",
        "your",
        "calculate",
        "tell",
        "give",
        "find",
        "get",
        "list",
        "display",
        "average",
        "mean",
        "total",
        "count",
        "number",
    }
)

_OOD_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bsquare\s+root\b",
        r"\bsqrt\b",
        r"\bbanana\b",
        r"\bsuper\s+bowl\b",
        r"\bwho\s+won\b",
    )
)

_TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


class RejectionKind(str, Enum):
    """Why a question was deemed not answerable."""

    ANSWERABLE = "answerable"
    CONCEPT_MISMATCH = "concept_mismatch"
    OUT_OF_DOMAIN = "out_of_domain"


@dataclass(frozen=True)
class AnswerabilityAssessment:
    """Deterministic guardrail outcome for a natural-language question."""

    answerable: bool
    kind: RejectionKind
    question: str
    matched_concepts: tuple[str, ...] = ()
    unmatched_concepts: tuple[str, ...] = ()
    reason: str = ""


def assess_answerability(
    question: str,
    *,
    lexicon: ConceptLexicon | None = None,
    models_dir: Path | None = None,
) -> AnswerabilityAssessment:
    """
    Return whether ``question`` can be answered from the semantic layer.

    When ``USE_LLM_ANSWERABILITY`` is enabled, an LLM classifier runs first;
    on failure the deterministic guardrail is used when fallback is enabled.
    """
    settings = get_settings()
    if settings.use_llm_answerability:
        from talk_to_data_slackbot.pandas_ai.answerability_classifier import (
            AnswerabilityClassifierError,
            assess_with_llm_classifier,
        )

        try:
            return assess_with_llm_classifier(
                question,
                models_dir=models_dir,
                settings=settings,
            )
        except AnswerabilityClassifierError as exc:
            if not settings.answerability_fallback_on_error:
                raise
            logging.warning(
                "LLM answerability classification failed; falling back to "
                "deterministic guardrail: %s",
                exc,
            )

    return _assess_deterministic(
        question,
        lexicon=lexicon,
        models_dir=models_dir,
    )


def _assess_deterministic(
    question: str,
    *,
    lexicon: ConceptLexicon | None = None,
    models_dir: Path | None = None,
) -> AnswerabilityAssessment:
    """
    Deterministic lexicon guardrail.

    Policy: reject if any business concept remains unmatched after synonym
    normalization and lexicon matching (precision over recall).
    """
    stripped = question.strip()
    if not stripped:
        return AnswerabilityAssessment(
            answerable=False,
            kind=RejectionKind.CONCEPT_MISMATCH,
            question=question,
            reason="Empty question.",
        )

    if _matches_out_of_domain(stripped):
        unmatched = _extract_unmatched(stripped, _resolve_lexicon(lexicon, models_dir))
        return AnswerabilityAssessment(
            answerable=False,
            kind=RejectionKind.OUT_OF_DOMAIN,
            question=question,
            unmatched_concepts=unmatched,
            reason="Question appears out of domain for business analytics.",
        )

    resolved_lexicon = _resolve_lexicon(lexicon, models_dir)
    matched, unmatched = _match_question(stripped, resolved_lexicon)

    if unmatched:
        return AnswerabilityAssessment(
            answerable=False,
            kind=RejectionKind.CONCEPT_MISMATCH,
            question=question,
            matched_concepts=matched,
            unmatched_concepts=unmatched,
            reason="Question references concepts not defined in the semantic layer.",
        )

    return AnswerabilityAssessment(
        answerable=True,
        kind=RejectionKind.ANSWERABLE,
        question=question,
        matched_concepts=matched,
        reason="All business concepts matched the semantic lexicon.",
    )


def _resolve_lexicon(
    lexicon: ConceptLexicon | None,
    models_dir: Path | None,
) -> ConceptLexicon:
    if lexicon is not None:
        return lexicon
    if models_dir is not None:
        return build_concept_lexicon(load_semantic_models(models_dir))
    return get_default_concept_lexicon()


def _matches_out_of_domain(question: str) -> bool:
    return any(pattern.search(question) for pattern in _OOD_PATTERNS)


def _match_question(
    question: str,
    lexicon: ConceptLexicon,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized = _normalize_question(question)
    normalized = apply_synonyms(normalized)
    remaining = f" {normalized} "

    matched: list[str] = []
    for phrase in lexicon.phrases:
        padded = f" {phrase} "
        while padded in remaining:
            matched.append(phrase)
            remaining = remaining.replace(padded, " ", 1)

    unmatched_tokens: list[str] = []
    for token in _TOKEN_PATTERN.findall(remaining):
        if token in _STOPWORDS or token in ANALYTICS_REQUEST_VOCABULARY:
            continue
        if token in lexicon.terms:
            matched.append(token)
            continue
        unmatched_tokens.append(token)

    matched_unique = tuple(sorted(set(matched)))
    unmatched_unique = tuple(sorted(set(unmatched_tokens)))
    return matched_unique, unmatched_unique


def _extract_unmatched(question: str, lexicon: ConceptLexicon) -> tuple[str, ...]:
    _, unmatched = _match_question(question, lexicon)
    return unmatched


def _normalize_question(question: str) -> str:
    lowered = question.lower()
    cleaned = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(cleaned.split())


__all__ = [
    "AnswerabilityAssessment",
    "RejectionKind",
    "assess_answerability",
    "clear_lexicon_cache",
]
