from __future__ import annotations

# Maintainer-approved request phrasing for the deterministic guardrail only.
# These terms are NOT semantic-layer concepts. Do not add to semantic_models YAML.
# Prefer promoting stable business dimensions to semantic aliases instead of growing this set.
MAX_ANALYTICS_VOCABULARY_ENTRIES = 35

VISUALIZATION_VOCABULARY = frozenset(
    {
        "plot",
        "chart",
        "graph",
        "visualize",
        "visualization",
        "trend",
    }
)

TIME_GROUPING_VOCABULARY = frozenset(
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

AGGREGATION_VOCABULARY = frozenset(
    {
        "count",
        "counts",
        "total",
        "totals",
    }
)

ANALYTICS_REQUEST_VOCABULARY = (
    VISUALIZATION_VOCABULARY | TIME_GROUPING_VOCABULARY | AGGREGATION_VOCABULARY
)
