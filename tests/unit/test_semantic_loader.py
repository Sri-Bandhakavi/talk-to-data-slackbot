from pathlib import Path

import pytest

from talk_to_data_slackbot.pandas_ai.semantic_loader import (
    SemanticModelValidationError,
    SemanticModelYamlError,
    SemanticModelsDirectoryNotFoundError,
    load_semantic_models,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "semantic_models"
VALID_DIR = FIXTURES_DIR / "valid"
REPO_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"


def test_load_valid_yaml_files() -> None:
    result = load_semantic_models(VALID_DIR)

    assert len(result.models) == 2
    by_name = result.by_name()
    assert set(by_name) == {"users", "subscriptions"}

    users = by_name["users"]
    assert users.source.table == "users"
    assert users.source.connection.host == "localhost"
    assert users.columns[1].alias == "region"
    assert users.columns[1].group_by is True
    assert users.source_file == VALID_DIR / "users.yaml"

    subscriptions = by_name["subscriptions"]
    assert len(subscriptions.relationships) == 1
    assert subscriptions.relationships[0].from_column == "user_id"
    assert subscriptions.relationships[0].to.dataset == "users"
    assert subscriptions.columns[-1].expression is not None


def test_load_repo_semantic_models() -> None:
    result = load_semantic_models(REPO_MODELS_DIR)

    assert len(result.models) == 4
    assert set(result.by_name()) == {
        "users",
        "subscriptions",
        "sessions",
        "payments",
    }


def test_invalid_yaml_raises_clear_error(tmp_path: Path) -> None:
    models_dir = tmp_path / "invalid_yaml"
    models_dir.mkdir()
    (models_dir / "broken.yaml").write_text("name: [\n", encoding="utf-8")

    with pytest.raises(SemanticModelYamlError, match="Invalid YAML"):
        load_semantic_models(models_dir)


def test_missing_required_fields_raises_clear_error(tmp_path: Path) -> None:
    models_dir = tmp_path / "missing_fields"
    models_dir.mkdir()
    (models_dir / "incomplete.yaml").write_text("description: only\n", encoding="utf-8")

    with pytest.raises(SemanticModelValidationError, match="missing required fields"):
        load_semantic_models(models_dir)


def test_missing_directory_raises_clear_error(tmp_path: Path) -> None:
    missing_dir = tmp_path / "does_not_exist"

    with pytest.raises(SemanticModelsDirectoryNotFoundError, match="not found"):
        load_semantic_models(missing_dir)


def test_empty_directory_raises_clear_error(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    with pytest.raises(SemanticModelsDirectoryNotFoundError, match="No semantic model YAML"):
        load_semantic_models(empty_dir)
