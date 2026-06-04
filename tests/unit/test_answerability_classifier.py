import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from talk_to_data_slackbot.config import Settings, get_settings
from talk_to_data_slackbot.pandas_ai.answerability import (
    AnswerabilityAssessment,
    RejectionKind,
    _assess_deterministic,
    assess_answerability,
)
from talk_to_data_slackbot.pandas_ai.answerability_classifier import (
    AnswerabilityClassifierError,
    _CLASSIFIER_POLICY,
    assess_with_llm_classifier,
    build_classifier_prompt,
    map_to_assessment,
    parse_classifier_response,
)
from talk_to_data_slackbot.pandas_ai.concept_lexicon import build_concept_lexicon
from talk_to_data_slackbot.pandas_ai.semantic_loader import load_semantic_models

REPO_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"


@pytest.fixture
def repo_lexicon():
    return build_concept_lexicon(load_semantic_models(REPO_MODELS_DIR))


@pytest.fixture
def llm_settings(settings_env: None, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("PANDASAI_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    return Settings()


def _valid_payload(
    *,
    answerable: bool,
    kind: str,
    unmatched_concepts: list[str] | None = None,
    reason: str = "test reason",
) -> str:
    return json.dumps(
        {
            "answerable": answerable,
            "kind": kind,
            "unmatched_concepts": unmatched_concepts or [],
            "reason": reason,
        }
    )


def test_classifier_policy_grounds_in_semantic_catalog() -> None:
    assert "ONLY the semantic catalog below" in _CLASSIFIER_POLICY
    assert "[alias:" in _CLASSIFIER_POLICY
    assert "relationships" in _CLASSIFIER_POLICY
    assert "executive" in _CLASSIFIER_POLICY.lower()


def test_classifier_policy_avoids_hardcoded_term_mappings() -> None:
    lowered = _CLASSIFIER_POLICY.lower()
    assert "money →" not in lowered and "money->" not in lowered
    assert "customers →" not in lowered and "customers->" not in lowered
    assert "sales →" not in lowered and "sales->" not in lowered


def test_build_classifier_prompt_includes_policy_catalog_and_question() -> None:
    prompt = build_classifier_prompt("revenue by region", "Dataset: payments")

    assert _CLASSIFIER_POLICY in prompt
    assert "Semantic catalog:\nDataset: payments" in prompt
    assert "Question: revenue by region" in prompt


def test_parse_classifier_response_accepts_valid_json() -> None:
    payload = parse_classifier_response(
        _valid_payload(answerable=True, kind="answerable")
    )

    assert payload["answerable"] is True
    assert payload["kind"] == "answerable"


def test_map_to_assessment_accepts_response() -> None:
    payload = parse_classifier_response(
        _valid_payload(answerable=True, kind="answerable", reason="All concepts match.")
    )
    assessment = map_to_assessment("revenue by region", payload)

    assert assessment.answerable is True
    assert assessment.kind is RejectionKind.ANSWERABLE
    assert assessment.question == "revenue by region"
    assert assessment.unmatched_concepts == ()
    assert assessment.reason == "All concepts match."


def test_assess_with_llm_classifier_reject_response() -> None:
    mock_llm = MagicMock()
    mock_llm.call.return_value = _valid_payload(
        answerable=False,
        kind="concept_mismatch",
        unmatched_concepts=["paying", "customers"],
        reason="Unsupported business concepts.",
    )

    assessment = assess_with_llm_classifier(
        "paying customers by region",
        models_dir=REPO_MODELS_DIR,
        llm=mock_llm,
    )

    assert assessment.answerable is False
    assert assessment.kind is RejectionKind.CONCEPT_MISMATCH
    assert assessment.unmatched_concepts == ("customers", "paying")


def test_assess_with_llm_classifier_out_of_domain_response() -> None:
    mock_llm = MagicMock()
    mock_llm.call.return_value = _valid_payload(
        answerable=False,
        kind="out_of_domain",
        reason="General knowledge question.",
    )

    assessment = assess_with_llm_classifier(
        "who won the Super Bowl",
        models_dir=REPO_MODELS_DIR,
        llm=mock_llm,
    )

    assert assessment.answerable is False
    assert assessment.kind is RejectionKind.OUT_OF_DOMAIN


def test_parse_classifier_response_invalid_json_raises() -> None:
    with pytest.raises(AnswerabilityClassifierError, match="Invalid JSON"):
        parse_classifier_response("not-json")


def test_parse_classifier_response_malformed_schema_raises() -> None:
    with pytest.raises(AnswerabilityClassifierError, match="missing required field"):
        parse_classifier_response('{"answerable": true}')

    with pytest.raises(AnswerabilityClassifierError, match="inconsistent"):
        parse_classifier_response(
            _valid_payload(answerable=True, kind="concept_mismatch")
        )


def test_assess_with_llm_classifier_llm_exception_raises() -> None:
    mock_llm = MagicMock()
    mock_llm.call.side_effect = RuntimeError("API unavailable")

    with pytest.raises(AnswerabilityClassifierError, match="LLM call failed"):
        assess_with_llm_classifier(
            "revenue by region",
            models_dir=REPO_MODELS_DIR,
            llm=mock_llm,
        )


def test_assess_with_llm_classifier_timeout_exception_raises() -> None:
    mock_llm = MagicMock()
    mock_llm.call.side_effect = TimeoutError("request timed out")

    with pytest.raises(AnswerabilityClassifierError, match="LLM call failed"):
        assess_with_llm_classifier(
            "revenue by region",
            models_dir=REPO_MODELS_DIR,
            llm=mock_llm,
        )


def test_assess_answerability_falls_back_to_deterministic_on_classifier_error(
    repo_lexicon,
    llm_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_LLM_ANSWERABILITY", "true")
    get_settings.cache_clear()

    expected = _assess_deterministic(
        "paying customers by region",
        lexicon=repo_lexicon,
    )

    with patch(
        "talk_to_data_slackbot.pandas_ai.answerability_classifier.assess_with_llm_classifier",
        side_effect=AnswerabilityClassifierError("invalid JSON"),
    ):
        assessment = assess_answerability(
            "paying customers by region",
            lexicon=repo_lexicon,
        )

    assert assessment == expected


def test_assess_answerability_uses_llm_path_when_enabled(
    llm_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USE_LLM_ANSWERABILITY", "true")
    get_settings.cache_clear()

    llm_assessment = AnswerabilityAssessment(
        answerable=True,
        kind=RejectionKind.ANSWERABLE,
        question="revenue by region",
        reason="LLM accepted.",
    )

    with patch(
        "talk_to_data_slackbot.pandas_ai.answerability_classifier.assess_with_llm_classifier",
        return_value=llm_assessment,
    ) as mock_classifier:
        assessment = assess_answerability("revenue by region")

    mock_classifier.assert_called_once()
    assert assessment is llm_assessment
