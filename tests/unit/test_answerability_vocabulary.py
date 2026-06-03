from talk_to_data_slackbot.pandas_ai.answerability_vocabulary import (
    AGGREGATION_VOCABULARY,
    ANALYTICS_REQUEST_VOCABULARY,
    MAX_ANALYTICS_VOCABULARY_ENTRIES,
    TIME_GROUPING_VOCABULARY,
    VISUALIZATION_VOCABULARY,
)


def test_analytics_vocabulary_contains_visualization_terms() -> None:
    assert VISUALIZATION_VOCABULARY == frozenset(
        {
            "plot",
            "chart",
            "graph",
            "visualize",
            "visualization",
            "trend",
        }
    )


def test_analytics_vocabulary_contains_time_grouping_terms() -> None:
    assert TIME_GROUPING_VOCABULARY == frozenset(
        {
            "month",
            "months",
            "year",
            "years",
            "quarter",
            "quarters",
            "monthly",
            "yearly",
            "quarterly",
            "date",
            "dates",
        }
    )


def test_analytics_vocabulary_contains_aggregation_terms() -> None:
    assert AGGREGATION_VOCABULARY == frozenset(
        {"count", "counts", "total", "totals"}
    )


def test_merged_analytics_vocabulary_size_cap() -> None:
    assert len(ANALYTICS_REQUEST_VOCABULARY) <= MAX_ANALYTICS_VOCABULARY_ENTRIES
    assert (
        VISUALIZATION_VOCABULARY
        | TIME_GROUPING_VOCABULARY
        | AGGREGATION_VOCABULARY
        == ANALYTICS_REQUEST_VOCABULARY
    )
