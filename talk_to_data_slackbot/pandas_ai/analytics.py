from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

from talk_to_data_slackbot.pandas_ai.semantic_loader import (
    ColumnDefinition,
    RelationshipDefinition,
    SemanticModelDefinition,
)

DEFAULT_DATASET_ORG = "public"
_SUPPORTED_DATABASE_SCHEMES = frozenset({"postgresql", "postgres"})


class DatabaseUrlError(ValueError):
    """Raised when DATABASE_URL cannot be parsed for PandasAI registration."""


@dataclass(frozen=True)
class PandasAICreateKwargs:
    """Keyword arguments for a single ``pai.create()`` registration call."""

    path: str
    description: str
    columns: list[dict[str, Any]]
    source: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "description": self.description,
            "columns": self.columns,
            "source": self.source,
        }


def parse_database_url(database_url: str) -> dict[str, Any]:
    """Parse ``DATABASE_URL`` into a PandasAI postgres ``connection`` dict."""
    parsed = urlparse(database_url.strip())

    if parsed.scheme not in _SUPPORTED_DATABASE_SCHEMES:
        raise DatabaseUrlError(
            f"Unsupported database URL scheme '{parsed.scheme}'. "
            f"Expected one of: {sorted(_SUPPORTED_DATABASE_SCHEMES)}"
        )

    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise DatabaseUrlError("DATABASE_URL must include a database name in the path")

    username = parsed.username
    if username is None:
        raise DatabaseUrlError("DATABASE_URL must include a username")

    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": unquote(username),
        "password": unquote(parsed.password or ""),
        "database": database,
    }


def to_pandasai_create_kwargs(
    model: SemanticModelDefinition,
    *,
    database_url: str,
    dataset_org: str = DEFAULT_DATASET_ORG,
) -> PandasAICreateKwargs:
    """Map a Component 2 semantic model to ``pai.create()`` registration kwargs."""
    connection = parse_database_url(database_url)
    return to_pandasai_create_kwargs_with_connection(
        model,
        connection=connection,
        dataset_org=dataset_org,
    )


def to_pandasai_create_kwargs_with_connection(
    model: SemanticModelDefinition,
    *,
    connection: dict[str, Any],
    dataset_org: str = DEFAULT_DATASET_ORG,
) -> PandasAICreateKwargs:
    """Map a semantic model using a pre-parsed postgres connection dict."""
    return PandasAICreateKwargs(
        path=f"{dataset_org}/{model.name}",
        description=_build_description(model),
        columns=[_map_column(column) for column in model.columns],
        source={
            "type": model.source.type,
            "table": model.source.table,
            "connection": connection,
        },
    )


def _build_description(model: SemanticModelDefinition) -> str:
    description = model.description.strip()
    join_hint = _format_join_hint(model.relationships)
    if join_hint:
        description = f"{description}\n\n{join_hint}"
    return description


def _format_join_hint(relationships: list[RelationshipDefinition]) -> str:
    if not relationships:
        return ""

    lines = [
        f"Joins to {relationship.to.dataset} on {relationship.from_column}."
        for relationship in relationships
    ]
    return "Join context:\n" + "\n".join(lines)


def _map_column(column: ColumnDefinition) -> dict[str, Any]:
    mapped: dict[str, Any] = {
        "name": column.name,
        "type": column.type,
        "description": _column_description(column),
    }
    if column.alias is not None:
        mapped["alias"] = column.alias
    if column.expression is not None:
        mapped["expression"] = _normalize_expression(column.expression)
    return mapped


def _column_description(column: ColumnDefinition) -> str:
    if column.group_by:
        return f"{column.description} (groupable dimension)"
    return column.description


def _normalize_expression(expression: str) -> str:
    return re.sub(r"\s+", " ", expression.strip())
