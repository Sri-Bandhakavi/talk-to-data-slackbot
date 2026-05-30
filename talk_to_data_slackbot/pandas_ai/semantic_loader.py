from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DEFAULT_SEMANTIC_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"


class SemanticLoaderError(Exception):
    """Base error for semantic model loading."""


class SemanticModelsDirectoryNotFoundError(SemanticLoaderError):
    """Raised when the semantic_models directory does not exist."""


class SemanticModelYamlError(SemanticLoaderError):
    """Raised when a semantic model file contains invalid YAML."""


class SemanticModelValidationError(SemanticLoaderError):
    """Raised when a semantic model file is missing required fields."""


class ConnectionDefinition(BaseModel):
    host: str
    port: int
    user: str
    password: str
    database: str


class SourceDefinition(BaseModel):
    type: str
    table: str
    connection: ConnectionDefinition


class RelationshipTarget(BaseModel):
    dataset: str
    column: str


class RelationshipDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_column: str = Field(alias="from")
    to: RelationshipTarget


class ColumnDefinition(BaseModel):
    name: str
    type: str
    description: str
    alias: str | None = None
    group_by: bool | None = None
    expression: str | None = None


class SemanticModelDefinition(BaseModel):
    name: str
    source: SourceDefinition
    description: str
    columns: list[ColumnDefinition]
    relationships: list[RelationshipDefinition] = Field(default_factory=list)
    source_file: Path | None = None

    @field_validator("columns")
    @classmethod
    def columns_must_not_be_empty(
        cls, columns: list[ColumnDefinition]
    ) -> list[ColumnDefinition]:
        if not columns:
            raise ValueError("columns must contain at least one column definition")
        return columns


class SemanticModelsLoadResult(BaseModel):
    models: list[SemanticModelDefinition]

    def by_name(self) -> dict[str, SemanticModelDefinition]:
        return {model.name: model for model in self.models}


def _resolve_models_dir(models_dir: Path | None) -> Path:
    return models_dir if models_dir is not None else DEFAULT_SEMANTIC_MODELS_DIR


def _discover_yaml_files(models_dir: Path) -> list[Path]:
    if not models_dir.is_dir():
        raise SemanticModelsDirectoryNotFoundError(
            f"Semantic models directory not found: {models_dir}"
        )

    yaml_files = sorted(models_dir.glob("*.yaml"))
    if not yaml_files:
        raise SemanticModelsDirectoryNotFoundError(
            f"No semantic model YAML files found in: {models_dir}"
        )

    return yaml_files


def _load_yaml_file(path: Path) -> Any:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SemanticModelYamlError(
            f"Unable to read semantic model file {path}: {exc}"
        ) from exc

    try:
        return yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise SemanticModelYamlError(
            f"Invalid YAML in semantic model file {path}: {exc}"
        ) from exc


def _parse_model(path: Path, data: Any) -> SemanticModelDefinition:
    if not isinstance(data, dict):
        raise SemanticModelValidationError(
            f"Semantic model file {path} must contain a YAML mapping at the top level"
        )

    try:
        model = SemanticModelDefinition.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise SemanticModelValidationError(
            f"Semantic model file {path} is missing required fields or has invalid values: "
            f"{details}"
        ) from exc

    return model.model_copy(update={"source_file": path})


def load_semantic_models(
    models_dir: Path | None = None,
) -> SemanticModelsLoadResult:
    """Discover and parse semantic model YAML files under semantic_models/."""
    resolved_dir = _resolve_models_dir(models_dir)
    yaml_files = _discover_yaml_files(resolved_dir)

    models: list[SemanticModelDefinition] = []
    seen_names: dict[str, Path] = {}

    for path in yaml_files:
        data = _load_yaml_file(path)
        if data is None:
            raise SemanticModelYamlError(
                f"Semantic model file {path} is empty"
            )

        model = _parse_model(path, data)

        if model.name in seen_names:
            previous = seen_names[model.name]
            raise SemanticModelValidationError(
                f"Duplicate semantic model name '{model.name}' in {path} "
                f"(already defined in {previous})"
            )

        seen_names[model.name] = path
        models.append(model)

    return SemanticModelsLoadResult(models=models)
