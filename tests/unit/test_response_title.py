from talk_to_data_slackbot.formatter.response_title import derive_response_title


def test_derive_response_title_strips_question_fillers() -> None:
    assert derive_response_title("Show revenue by region") == "Revenue Region"
    assert derive_response_title("How many users signed up?") == "Users Signed Up"


def test_derive_response_title_applies_synonyms() -> None:
    assert derive_response_title("Show revenue by geography") == "Revenue Region"


def test_derive_response_title_strips_analytics_vocabulary() -> None:
    assert derive_response_title("Plot signups over time") == "Signups Over Time"
    assert derive_response_title("Monthly revenue trend by plan") == "Revenue Plan"


def test_derive_response_title_preserves_business_terms() -> None:
    assert derive_response_title("Users by country") == "Users Country"
    assert derive_response_title("Active subscriptions by region") == "Active Subscriptions Region"


def test_derive_response_title_fallback_for_empty_question() -> None:
    assert derive_response_title("   ") == "Question"


def test_derive_response_title_fallback_when_only_fillers_remain() -> None:
    assert derive_response_title("show me") == "Show Me"
