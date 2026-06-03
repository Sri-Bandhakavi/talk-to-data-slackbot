from talk_to_data_slackbot.pandas_ai.answerability_synonyms import (
    MAX_SYNONYM_ENTRIES,
    QUESTION_TERM_SYNONYMS,
    apply_synonyms,
)


def test_synonym_map_is_small_and_frozen() -> None:
    assert len(QUESTION_TERM_SYNONYMS) <= MAX_SYNONYM_ENTRIES
    assert QUESTION_TERM_SYNONYMS == {
        "customer": "user",
        "geography": "region",
        "device": "platform",
    }


def test_apply_synonyms_customer_to_user() -> None:
    assert apply_synonyms("Customer count by region") == "User count by region"


def test_apply_synonyms_plural_customer() -> None:
    assert apply_synonyms("Paying customers by region") == "Paying users by region"


def test_apply_synonyms_geography_to_region() -> None:
    assert apply_synonyms("Revenue by geography") == "Revenue by region"


def test_apply_synonyms_device_to_platform() -> None:
    assert apply_synonyms("Signups by device") == "Signups by platform"
