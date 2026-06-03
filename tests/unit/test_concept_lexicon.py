from pathlib import Path

from talk_to_data_slackbot.pandas_ai.concept_lexicon import build_concept_lexicon
from talk_to_data_slackbot.pandas_ai.semantic_loader import load_semantic_models

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "semantic_models"
VALID_DIR = FIXTURES_DIR / "valid"
REPO_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"


def test_build_lexicon_from_fixture_models() -> None:
    lexicon = build_concept_lexicon(load_semantic_models(VALID_DIR))

    assert "users" in lexicon.terms
    assert "subscriptions" in lexicon.terms
    assert "region" in lexicon.terms
    assert "country" in lexicon.terms
    assert "subscription length days" in lexicon.phrases or (
        "subscription_length_days" in lexicon.terms
    )


def test_build_lexicon_from_repo_models_includes_core_concepts() -> None:
    lexicon = build_concept_lexicon(load_semantic_models(REPO_MODELS_DIR))

    for term in (
        "users",
        "subscriptions",
        "sessions",
        "payments",
        "revenue",
        "region",
        "platform",
        "churn",
        "plan",
    ):
        assert term in lexicon.terms

    for phrase in (
        "active subscriptions",
        "subscription churn",
        "revenue by region",
        "total revenue",
    ):
        assert phrase in lexicon.phrases
