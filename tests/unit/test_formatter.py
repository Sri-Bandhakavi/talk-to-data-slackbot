from talk_to_data_slackbot.formatter import (
    FormattedMessage,
    derive_response_title,
    format_guardrail_rejection,
    format_response,
)
from talk_to_data_slackbot.formatter.slack import (
    MAX_BLOCK_TEXT_CHARS,
    MAX_FALLBACK_TEXT_CHARS,
    _TRUNCATION_SUFFIX,
)
from talk_to_data_slackbot.pandas_ai.analytics import AgentResult
from talk_to_data_slackbot.pandas_ai.answerability import (
    RejectionKind,
    assess_answerability,
)


def _block_text(formatted: FormattedMessage) -> str:
    assert formatted.blocks is not None
    assert len(formatted.blocks) == 1
    block = formatted.blocks[0]
    assert block["type"] == "section"
    return block["text"]["text"]


def test_format_text_success() -> None:
    result = AgentResult(
        success=True,
        result_type="text",
        value="There are 42 users signed up.",
        question="How many users signed up?",
    )

    formatted = format_response(result)
    expected_body = "*Answer*\n\nThere are 42 users signed up."

    assert formatted == FormattedMessage(
        text=expected_body,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": expected_body,
                },
            }
        ],
        chart_path=None,
        title="Users Signed Up",
    )
    assert formatted.chart_path is None
    assert formatted.title == derive_response_title(result.question)


def test_format_dataframe_success() -> None:
    table = "country  users\nUS       10\nCA       5"
    result = AgentResult(
        success=True,
        result_type="dataframe",
        value=table,
        question="Users by country",
    )

    formatted = format_response(result)
    expected_body = f"*Results*\n\n```{table}```"

    assert formatted.text == expected_body
    assert _block_text(formatted) == expected_body
    assert formatted.chart_path is None
    assert formatted.title == "Users Country"


def test_format_chart_success() -> None:
    result = AgentResult(
        success=True,
        result_type="chart",
        value="/tmp/signups_chart.png",
        question="Plot signups over time",
    )

    formatted = format_response(result)
    expected_body = "*Chart*\n\nI've generated a chart for your question."

    assert formatted.text == expected_body
    assert formatted.chart_path == "/tmp/signups_chart.png"
    assert _block_text(formatted) == expected_body
    assert formatted.title == "Signups Over Time"


def test_format_error_result() -> None:
    result = AgentResult(
        success=False,
        result_type="error",
        value="Something went wrong while running your analytics question. Please try again.",
        question="Bad question",
        error_detail="RuntimeError: agent execution failed",
    )

    formatted = format_response(result)

    assert formatted.text == (
        "Something went wrong while running your analytics question. Please try again."
    )
    assert _block_text(formatted) == formatted.text
    assert formatted.chart_path is None
    assert formatted.title is None
    assert "RuntimeError" not in formatted.text
    assert "RuntimeError" not in _block_text(formatted)


def test_format_empty_value() -> None:
    result = AgentResult(
        success=True,
        result_type="text",
        value="   ",
        question="Empty answer",
    )

    formatted = format_response(result)

    assert formatted.text == "No results returned."
    assert _block_text(formatted) == "No results returned."
    assert formatted.title == "Empty Answer"


def _guardrail_body(formatted: FormattedMessage) -> str:
    return _block_text(formatted)


def test_format_guardrail_rejection_out_of_domain_sqrt_banana() -> None:
    assessment = assess_answerability("calculate the square root of banana")
    formatted = format_guardrail_rejection(assessment)

    assert assessment.kind is RejectionKind.OUT_OF_DOMAIN
    expected = (
        "*Can't answer from available data*\n\n"
        "I can't answer that from the business data available in this workspace.\n\n"
        "Here are some things I can help with:\n"
        "• Revenue and payment trends\n"
        "• Active subscriptions and churn\n"
        "• Users and signups by region or platform\n"
        "• Session engagement and duration"
    )
    assert formatted.text == expected
    assert _guardrail_body(formatted) == expected
    assert formatted.title is None
    assert "banana" not in formatted.text
    assert "Unrecognized" not in formatted.text


def test_format_guardrail_rejection_concept_mismatch_satisfaction_category() -> None:
    question = "Show average customer satisfaction score by product category"
    assessment = assess_answerability(question)
    formatted = format_guardrail_rejection(assessment)

    assert assessment.kind is RejectionKind.CONCEPT_MISMATCH
    expected = (
        "*Can't answer from available data*\n\n"
        "I can't answer that from the business data available in this workspace.\n\n"
        "Unrecognized in your question: category, product, satisfaction, score\n\n"
        "Here are some questions I can answer with the current data:\n"
        "• Revenue by region or subscription plan\n"
        "• Churn and active subscriptions\n"
        "• Average subscription length\n"
        "• Users and signups by region or platform"
    )
    assert formatted.text == expected
    assert _guardrail_body(formatted) == expected
    assert formatted.title is None


def test_format_guardrail_rejection_concept_mismatch_paying_customers() -> None:
    question = "Show paying customers by region"
    assessment = assess_answerability(question)
    formatted = format_guardrail_rejection(assessment)

    assert assessment.kind is RejectionKind.CONCEPT_MISMATCH
    expected = (
        "*Can't answer from available data*\n\n"
        "I can't answer that from the business data available in this workspace.\n\n"
        "Unrecognized in your question: paying\n\n"
        "Here are some questions I can answer with the current data:\n"
        "• Revenue by region or subscription plan\n"
        "• Churn and active subscriptions\n"
        "• Average subscription length\n"
        "• Users and signups by region or platform"
    )
    assert formatted.text == expected
    assert _guardrail_body(formatted) == expected
    assert formatted.title is None


def test_format_truncates_long_text_for_fallback_and_block() -> None:
    long_answer = "A" * 5000
    result = AgentResult(
        success=True,
        result_type="text",
        value=long_answer,
        question="Long answer",
    )

    formatted = format_response(result)

    assert len(formatted.text) <= MAX_FALLBACK_TEXT_CHARS
    assert formatted.text.endswith(_TRUNCATION_SUFFIX)
    assert "*Answer*" in formatted.text
    assert formatted.text.startswith("*Answer*\n\nA")

    block_text = _block_text(formatted)
    assert len(block_text) <= MAX_BLOCK_TEXT_CHARS
    assert block_text.endswith(_TRUNCATION_SUFFIX)
    assert block_text.startswith("*Answer*\n\nA")
    assert formatted.title == "Long Answer"
