from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from talk_to_data_slackbot.formatter.response_title import derive_response_title
from talk_to_data_slackbot.pandas_ai.analytics import AgentResult
from talk_to_data_slackbot.pandas_ai.answerability import (
    AnswerabilityAssessment,
    RejectionKind,
)

MAX_FALLBACK_TEXT_CHARS = 3900
MAX_BLOCK_TEXT_CHARS = 2900
_TRUNCATION_SUFFIX = "\n\n_(Results truncated for Slack.)_"
_EMPTY_RESULT_MESSAGE = "No results returned."
_CHART_MESSAGE = "I've generated a chart for your question."

_TEXT_HEADER = "*Answer*"
_TABLE_HEADER = "*Results*"
_CHART_HEADER = "*Chart*"
_GUARDRAIL_HEADER = "*Can't answer from available data*"
_GUARDRAIL_LEAD = (
    "I can't answer that from the business data available in this workspace."
)
_OOD_SUGGESTION_BULLETS = (
    "• Revenue and payment trends",
    "• Active subscriptions and churn",
    "• Users and signups by region or platform",
    "• Session engagement and duration",
)
_CONCEPT_SUGGESTION_BULLETS = (
    "• Revenue by region or subscription plan",
    "• Churn and active subscriptions",
    "• Average subscription length",
    "• Users and signups by region or platform",
)


@dataclass(frozen=True)
class FormattedMessage:
    """Slack-ready payload produced by Formatter for Router and Intake."""

    text: str
    blocks: list[dict[str, Any]] | None = None
    chart_path: str | None = None
    title: str | None = None


def format_guardrail_rejection(assessment: AnswerabilityAssessment) -> FormattedMessage:
    """Format a deterministic guardrail rejection for Slack."""
    body = _format_guardrail_rejection_body(assessment)
    block_text = _truncate(body, MAX_BLOCK_TEXT_CHARS)
    fallback_text = _truncate(body, MAX_FALLBACK_TEXT_CHARS)

    return FormattedMessage(
        text=fallback_text,
        blocks=[_section_block(block_text)],
    )


def format_response(result: AgentResult) -> FormattedMessage:
    """Map an ``AgentResult`` into a Slack-safe ``FormattedMessage``."""
    if not result.success or result.result_type == "error":
        return _format_error(result)

    if result.result_type == "chart":
        return _format_chart(result)

    body = _format_success_body(result)
    block_text = _truncate(body, MAX_BLOCK_TEXT_CHARS)
    fallback_text = _truncate(body, MAX_FALLBACK_TEXT_CHARS)

    return FormattedMessage(
        text=fallback_text,
        blocks=[_section_block(block_text)],
        title=derive_response_title(result.question),
    )


def _format_guardrail_rejection_body(assessment: AnswerabilityAssessment) -> str:
    sections = [_GUARDRAIL_HEADER, "", _GUARDRAIL_LEAD]

    if assessment.kind is RejectionKind.CONCEPT_MISMATCH and assessment.unmatched_concepts:
        unmatched = ", ".join(assessment.unmatched_concepts)
        sections.extend(["", f"Unrecognized in your question: {unmatched}"])

    if assessment.kind is RejectionKind.OUT_OF_DOMAIN:
        sections.extend(
            [
                "",
                "Here are some things I can help with:",
                *_OOD_SUGGESTION_BULLETS,
            ]
        )
    else:
        sections.extend(
            [
                "",
                "Here are some questions I can answer with the current data:",
                *_CONCEPT_SUGGESTION_BULLETS,
            ]
        )

    return "\n".join(sections)


def _format_error(result: AgentResult) -> FormattedMessage:
    message = str(result.value).strip() or _EMPTY_RESULT_MESSAGE
    block_text = _truncate(message, MAX_BLOCK_TEXT_CHARS)
    fallback_text = _truncate(message, MAX_FALLBACK_TEXT_CHARS)

    return FormattedMessage(
        text=fallback_text,
        blocks=[_section_block(block_text)],
    )


def _format_chart(result: AgentResult) -> FormattedMessage:
    chart_path = str(result.value).strip() or None
    body = f"{_CHART_HEADER}\n\n{_CHART_MESSAGE}"
    block_text = _truncate(body, MAX_BLOCK_TEXT_CHARS)
    fallback_text = _truncate(body, MAX_FALLBACK_TEXT_CHARS)

    return FormattedMessage(
        text=fallback_text,
        blocks=[_section_block(block_text)],
        chart_path=chart_path,
        title=derive_response_title(result.question),
    )


def _format_success_body(result: AgentResult) -> str:
    if result.result_type == "dataframe":
        table = str(result.value).strip()
        if not table:
            return _EMPTY_RESULT_MESSAGE
        return f"{_TABLE_HEADER}\n\n```{table}```"

    text = str(result.value).strip()
    if not text:
        return _EMPTY_RESULT_MESSAGE
    return f"{_TEXT_HEADER}\n\n{text}"


def _section_block(text: str) -> dict[str, Any]:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    suffix_budget = len(_TRUNCATION_SUFFIX)
    if max_chars <= suffix_budget:
        return text[:max_chars]

    return text[: max_chars - suffix_budget] + _TRUNCATION_SUFFIX
