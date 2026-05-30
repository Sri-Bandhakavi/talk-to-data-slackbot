from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from talk_to_data_slackbot import postgres
from talk_to_data_slackbot.pandas_ai.semantic_loader import (
    SemanticModelDefinition,
    SemanticModelsLoadResult,
)

SCHEMA = "public"

TABLES_SQL = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = %(schema)s
  AND table_type = 'BASE TABLE'
"""

COLUMNS_SQL = """
SELECT column_name
FROM information_schema.columns
WHERE table_schema = %(schema)s
  AND table_name = %(table)s
"""

IssueType = Literal["unknown_table", "unknown_column"]


@dataclass(frozen=True)
class SemanticValidationIssue:
    model_name: str
    issue_type: IssueType
    message: str
    source_file: Path | None = None


@dataclass
class SemanticValidationResult:
    models_checked: int
    issues: list[SemanticValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _fetch_tables() -> set[str]:
    rows = postgres.execute_read(TABLES_SQL, {"schema": SCHEMA})
    return {row["table_name"] for row in rows}


def _fetch_columns(table: str) -> set[str]:
    rows = postgres.execute_read(COLUMNS_SQL, {"schema": SCHEMA, "table": table})
    return {row["column_name"] for row in rows}


def _validate_model(
    model: SemanticModelDefinition,
    tables: set[str],
    columns_by_table: dict[str, set[str]],
) -> list[SemanticValidationIssue]:
    issues: list[SemanticValidationIssue] = []
    table = model.source.table

    if table not in tables:
        issues.append(
            SemanticValidationIssue(
                model_name=model.name,
                source_file=model.source_file,
                issue_type="unknown_table",
                message=(
                    f"Table '{table}' declared in model '{model.name}' "
                    f"not found in {SCHEMA} schema"
                ),
            )
        )
        return issues

    if table not in columns_by_table:
        columns_by_table[table] = _fetch_columns(table)

    db_columns = columns_by_table[table]
    for column in model.columns:
        if column.expression:
            continue
        if column.name not in db_columns:
            issues.append(
                SemanticValidationIssue(
                    model_name=model.name,
                    source_file=model.source_file,
                    issue_type="unknown_column",
                    message=(
                        f"Column '{column.name}' on table '{table}' declared in model "
                        f"'{model.name}' not found in PostgreSQL"
                    ),
                )
            )

    return issues


def validate_semantic_models(
    models: SemanticModelsLoadResult,
) -> SemanticValidationResult:
    """Contract-check loaded semantic models against PostgreSQL metadata."""
    tables = _fetch_tables()
    columns_by_table: dict[str, set[str]] = {}
    issues: list[SemanticValidationIssue] = []

    for model in models.models:
        issues.extend(_validate_model(model, tables, columns_by_table))

    return SemanticValidationResult(
        models_checked=len(models.models),
        issues=issues,
    )
