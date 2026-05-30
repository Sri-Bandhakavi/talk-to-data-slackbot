from pathlib import Path

import pytest

from talk_to_data_slackbot.config import get_settings
from talk_to_data_slackbot.pandas_ai.semantic_loader import load_semantic_models
from talk_to_data_slackbot.pandas_ai.semantic_validator import validate_semantic_models

pytestmark = pytest.mark.integration

REPO_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"

MINIMAL_MODEL_YAML = """\
name: {name}

source:
  type: postgres
  table: {table}
  connection:
    host: localhost
    port: 5432
    user: test
    password: test
    database: testdb

description: Test model for semantic validator contract tests.

columns:
  - name: user_id
    type: integer
    description: Unique identifier for the user
{extra_columns}
"""


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _write_model(
    models_dir: Path,
    *,
    name: str = "users",
    table: str = "users",
    extra_columns: str = "",
) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    content = MINIMAL_MODEL_YAML.format(
        name=name,
        table=table,
        extra_columns=extra_columns,
    )
    (models_dir / f"{name}.yaml").write_text(content, encoding="utf-8")


def test_validate_repo_models_passes(database_url: str) -> None:
    models = load_semantic_models(REPO_MODELS_DIR)
    result = validate_semantic_models(models)

    assert result.is_valid is True
    assert result.issues == []
    assert result.models_checked == 4


def test_validate_unknown_table(database_url: str, tmp_path: Path) -> None:
    _write_model(tmp_path, table="nonexistent_table_xyz")

    models = load_semantic_models(tmp_path)
    result = validate_semantic_models(models)

    assert result.is_valid is False
    assert len(result.issues) == 1
    assert result.issues[0].issue_type == "unknown_table"
    assert "nonexistent_table_xyz" in result.issues[0].message


def test_validate_unknown_column(database_url: str, tmp_path: Path) -> None:
    extra_columns = """
  - name: not_a_real_column
    type: string
    description: Column that does not exist in PostgreSQL
"""
    _write_model(tmp_path, extra_columns=extra_columns)

    models = load_semantic_models(tmp_path)
    result = validate_semantic_models(models)

    assert result.is_valid is False
    assert len(result.issues) == 1
    assert result.issues[0].issue_type == "unknown_column"
    assert "not_a_real_column" in result.issues[0].message
