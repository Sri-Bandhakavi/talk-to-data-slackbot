from pathlib import Path

import pytest

from talk_to_data_slackbot.pandas_ai.answerability import (
    RejectionKind,
    assess_answerability,
)
from talk_to_data_slackbot.pandas_ai.concept_lexicon import build_concept_lexicon
from talk_to_data_slackbot.pandas_ai.semantic_loader import load_semantic_models

REPO_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"


@pytest.fixture
def repo_lexicon():
    return build_concept_lexicon(load_semantic_models(REPO_MODELS_DIR))


def _assess(question: str, repo_lexicon):
    return assess_answerability(question, lexicon=repo_lexicon)


@pytest.mark.parametrize(
    "question",
    [
        "active subscriptions by region",
        "revenue by geography",
        "revenue by region",
        "churn by region",
    ],
)
def test_assess_answerability_accepts_supported_questions(
    question: str,
    repo_lexicon,
) -> None:
    assessment = _assess(question, repo_lexicon)

    assert assessment.answerable is True
    assert assessment.kind is RejectionKind.ANSWERABLE
    assert assessment.unmatched_concepts == ()


@pytest.mark.parametrize(
    "question",
    [
        "paying customers by region",
        "customer satisfaction score by product category",
        "calculate the square root of banana",
        "who won the Super Bowl",
        "satisfaction by plan",
    ],
)
def test_assess_answerability_rejects_unsupported_questions(
    question: str,
    repo_lexicon,
) -> None:
    assessment = _assess(question, repo_lexicon)

    assert assessment.answerable is False
    assert assessment.kind in {
        RejectionKind.CONCEPT_MISMATCH,
        RejectionKind.OUT_OF_DOMAIN,
    }
    assert assessment.unmatched_concepts or assessment.kind is RejectionKind.OUT_OF_DOMAIN


def test_reject_paying_customers_flags_paying(repo_lexicon) -> None:
    assessment = _assess("paying customers by region", repo_lexicon)

    assert assessment.answerable is False
    assert "paying" in assessment.unmatched_concepts


def test_reject_satisfaction_by_plan_flags_satisfaction(repo_lexicon) -> None:
    assessment = _assess("satisfaction by plan", repo_lexicon)

    assert assessment.answerable is False
    assert "satisfaction" in assessment.unmatched_concepts


def test_reject_product_category_question_flags_unsupported_terms(repo_lexicon) -> None:
    assessment = _assess(
        "customer satisfaction score by product category",
        repo_lexicon,
    )

    assert assessment.answerable is False
    assert "satisfaction" in assessment.unmatched_concepts
    assert "product" in assessment.unmatched_concepts or "category" in assessment.unmatched_concepts


def test_reject_sqrt_banana_is_out_of_domain(repo_lexicon) -> None:
    assessment = _assess("calculate the square root of banana", repo_lexicon)

    assert assessment.answerable is False
    assert assessment.kind is RejectionKind.OUT_OF_DOMAIN
