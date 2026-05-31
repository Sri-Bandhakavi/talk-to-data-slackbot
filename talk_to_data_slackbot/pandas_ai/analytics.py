from __future__ import annotations

import hashlib
import json
import re
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import pandas as pd
import pandasai as pai
from pandasai import Agent
from pandasai.helpers.path import find_project_root

from talk_to_data_slackbot.config import Settings, get_settings
from talk_to_data_slackbot.pandas_ai.llm import LLMConfigurationError, configure_llm
from talk_to_data_slackbot.pandas_ai.semantic_loader import (
    ColumnDefinition,
    RelationshipDefinition,
    SemanticModelDefinition,
    load_semantic_models,
)

DEFAULT_DATASET_ORG = "public"
EXPECTED_DATASET_NAMES = frozenset(
    {"users", "subscriptions", "sessions", "payments"}
)
_FINGERPRINT_FILENAME = ".registration_fingerprint"
_SUPPORTED_DATABASE_SCHEMES = frozenset({"postgresql", "postgres"})


class DatabaseUrlError(ValueError):
    """Raised when DATABASE_URL cannot be parsed for PandasAI registration."""


class DatasetRegistrationError(Exception):
    """Raised when semantic model dataset registration cannot proceed."""


AgentResultType = Literal["text", "dataframe", "chart", "error"]

_USER_FACING_LLM_ERROR = (
    "Analytics is not configured. Set OPENAI_API_KEY before running queries."
)
_USER_FACING_DATASET_ERROR = (
    "Unable to prepare datasets for analytics. Check DATABASE_URL and semantic models."
)
_USER_FACING_DATABASE_URL_ERROR = (
    "Database connection settings are invalid. Check DATABASE_URL."
)
_USER_FACING_QUERY_ERROR = (
    "Something went wrong while running your analytics question. Please try again."
)


@dataclass(frozen=True)
class AgentResult:
    """Application-facing analytics result for Router and Formatter."""

    success: bool
    result_type: AgentResultType
    value: str | Any
    question: str
    error_detail: str | None = None


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


@dataclass(frozen=True)
class DatasetRegistrationPlan:
    """Planned ``pai.create()`` registration for one semantic model."""

    path: str
    create_kwargs: PandasAICreateKwargs
    fingerprint: str


def compute_registration_fingerprint(
    create_kwargs: PandasAICreateKwargs,
) -> str:
    """Hash adapter output used to detect stale PandasAI local cache entries."""
    payload = json.dumps(create_kwargs.as_dict(), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_registration_plans(
    *,
    database_url: str,
    models_dir: Path | None = None,
    dataset_org: str = DEFAULT_DATASET_ORG,
) -> list[DatasetRegistrationPlan]:
    """Build registration plans from semantic models without calling PandasAI."""
    result = load_semantic_models(models_dir)
    plans: list[DatasetRegistrationPlan] = []

    for model in sorted(result.models, key=lambda item: item.name):
        create_kwargs = to_pandasai_create_kwargs(
            model,
            database_url=database_url,
            dataset_org=dataset_org,
        )
        plans.append(
            DatasetRegistrationPlan(
                path=create_kwargs.path,
                create_kwargs=create_kwargs,
                fingerprint=compute_registration_fingerprint(create_kwargs),
            )
        )

    return plans


def build_datasets(
    *,
    database_url: str | None = None,
    models_dir: Path | None = None,
    datasets_root: Path | None = None,
    expected_models: frozenset[str] | None = EXPECTED_DATASET_NAMES,
) -> list[Any]:
    """Register semantic models with PandasAI v3 and return dataset handles."""
    resolved_url = database_url or get_settings().database_url
    root = datasets_root or Path(find_project_root()) / "datasets"
    plans = build_registration_plans(
        database_url=resolved_url,
        models_dir=models_dir,
    )

    if expected_models is not None:
        loaded_names = frozenset(_dataset_name_from_path(plan.path) for plan in plans)
        if loaded_names != expected_models:
            missing = sorted(expected_models - loaded_names)
            extra = sorted(loaded_names - expected_models)
            details: list[str] = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if extra:
                details.append(f"unexpected: {', '.join(extra)}")
            raise DatasetRegistrationError(
                "Semantic model set does not match expected datasets "
                f"({'; '.join(details)})"
            )

    return [_register_dataset(plan, datasets_root=root) for plan in plans]


def _dataset_name_from_path(path: str) -> str:
    return path.split("/", 1)[1]


def _dataset_cache_dir(datasets_root: Path, path: str) -> Path:
    return datasets_root.joinpath(*path.split("/"))


def _read_cached_fingerprint(cache_dir: Path) -> str | None:
    fingerprint_path = cache_dir / _FINGERPRINT_FILENAME
    if not fingerprint_path.is_file():
        return None
    return fingerprint_path.read_text(encoding="utf-8").strip()


def _write_cached_fingerprint(cache_dir: Path, fingerprint: str) -> None:
    fingerprint_path = cache_dir / _FINGERPRINT_FILENAME
    fingerprint_path.write_text(fingerprint, encoding="utf-8")


def _remove_dataset_cache(cache_dir: Path) -> None:
    if cache_dir.exists():
        shutil.rmtree(cache_dir)


def _register_dataset(
    plan: DatasetRegistrationPlan,
    *,
    datasets_root: Path,
) -> Any:
    """Create or load one PandasAI dataset based on registration fingerprint."""
    cache_dir = _dataset_cache_dir(datasets_root, plan.path)
    schema_path = cache_dir / "schema.yaml"
    cached_fingerprint = _read_cached_fingerprint(cache_dir)

    if schema_path.is_file() and cached_fingerprint == plan.fingerprint:
        return pai.load(plan.path)

    _remove_dataset_cache(cache_dir)
    dataset = pai.create(**plan.create_kwargs.as_dict())
    cache_dir.mkdir(parents=True, exist_ok=True)
    _write_cached_fingerprint(cache_dir, plan.fingerprint)
    return dataset


def build_agent(
    *,
    settings: Settings | None = None,
    database_url: str | None = None,
    models_dir: Path | None = None,
    datasets_root: Path | None = None,
    expected_models: frozenset[str] | None = EXPECTED_DATASET_NAMES,
) -> Agent:
    """Configure LLM, register semantic datasets, and return a PandasAI v3 Agent."""
    configure_llm(settings)
    datasets = build_datasets(
        database_url=database_url,
        models_dir=models_dir,
        datasets_root=datasets_root,
        expected_models=expected_models,
    )
    if not datasets:
        raise DatasetRegistrationError(
            "No datasets registered for Agent construction"
        )
    return Agent(datasets)


def run_query(
    question: str,
    *,
    settings: Settings | None = None,
    database_url: str | None = None,
    models_dir: Path | None = None,
    datasets_root: Path | None = None,
    expected_models: frozenset[str] | None = EXPECTED_DATASET_NAMES,
) -> AgentResult:
    """Run a natural-language analytics question through the PandasAI v3 Agent."""
    try:
        agent = build_agent(
            settings=settings,
            database_url=database_url,
            models_dir=models_dir,
            datasets_root=datasets_root,
            expected_models=expected_models,
        )
        response = agent.chat(question)
        return normalize_agent_response(question, response)
    except LLMConfigurationError as exc:
        return _error_result(question, _USER_FACING_LLM_ERROR, str(exc))
    except DatasetRegistrationError as exc:
        return _error_result(question, _USER_FACING_DATASET_ERROR, str(exc))
    except DatabaseUrlError as exc:
        return _error_result(question, _USER_FACING_DATABASE_URL_ERROR, str(exc))
    except Exception as exc:
        return _error_result(
            question,
            _USER_FACING_QUERY_ERROR,
            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )


def normalize_agent_response(question: str, response: Any) -> AgentResult:
    """Map a PandasAI Agent response object into an ``AgentResult``."""
    response_type = getattr(response, "type", None)
    value = getattr(response, "value", response)
    error_detail = getattr(response, "error", None)

    if response_type == "error":
        return AgentResult(
            success=False,
            result_type="error",
            value=str(value),
            question=question,
            error_detail=error_detail or str(value),
        )

    if response_type == "string":
        return AgentResult(
            success=True,
            result_type="text",
            value=str(value),
            question=question,
        )

    if response_type == "number":
        return AgentResult(
            success=True,
            result_type="text",
            value=str(value),
            question=question,
        )

    if response_type == "dataframe":
        return AgentResult(
            success=True,
            result_type="dataframe",
            value=_format_dataframe(value),
            question=question,
        )

    if response_type == "chart":
        return AgentResult(
            success=True,
            result_type="chart",
            value=_format_chart(value),
            question=question,
        )

    if isinstance(response, str):
        return AgentResult(
            success=True,
            result_type="text",
            value=response,
            question=question,
        )

    return AgentResult(
        success=True,
        result_type="text",
        value=str(response),
        question=question,
    )


def _error_result(
    question: str,
    user_message: str,
    error_detail: str,
) -> AgentResult:
    return AgentResult(
        success=False,
        result_type="error",
        value=user_message,
        question=question,
        error_detail=error_detail,
    )


def _format_dataframe(value: Any) -> str:
    if isinstance(value, pd.Series):
        frame = value.to_frame()
    elif isinstance(value, pd.DataFrame):
        frame = value
    else:
        return str(value)

    return frame.to_string(index=False)


def _format_chart(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)
