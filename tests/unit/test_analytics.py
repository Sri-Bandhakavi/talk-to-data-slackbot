from pathlib import Path

import pytest

from talk_to_data_slackbot.pandas_ai.analytics import (
    DatabaseUrlError,
    parse_database_url,
    to_pandasai_create_kwargs,
)
from talk_to_data_slackbot.pandas_ai.semantic_loader import load_semantic_models

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "semantic_models" / "valid"
REPO_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"
TEST_DATABASE_URL = "postgresql://runtime_user:runtime_pass@db.example.com:5433/runtime_db"


def test_parse_database_url_standard_postgresql() -> None:
    connection = parse_database_url(
        "postgresql://students:secret%40word@host.example.com:5432/beam_neb0"
    )

    assert connection == {
        "host": "host.example.com",
        "port": 5432,
        "user": "students",
        "password": "secret@word",
        "database": "beam_neb0",
    }


def test_parse_database_url_defaults_port_and_localhost() -> None:
    connection = parse_database_url("postgres://user:pass@/mydb")

    assert connection["host"] == "localhost"
    assert connection["port"] == 5432
    assert connection["database"] == "mydb"


def test_parse_database_url_rejects_unsupported_scheme() -> None:
    with pytest.raises(DatabaseUrlError, match="Unsupported database URL scheme"):
        parse_database_url("mysql://user:pass@localhost/db")


def test_parse_database_url_requires_database_name() -> None:
    with pytest.raises(DatabaseUrlError, match="database name"):
        parse_database_url("postgresql://user:pass@localhost:5432/")


def test_parse_database_url_requires_username() -> None:
    with pytest.raises(DatabaseUrlError, match="username"):
        parse_database_url("postgresql://localhost/testdb")


def test_users_model_maps_to_top_level_pandasai_create_kwargs() -> None:
    users = load_semantic_models(FIXTURES_DIR).by_name()["users"]
    kwargs = to_pandasai_create_kwargs(users, database_url=TEST_DATABASE_URL)

    assert kwargs.path == "public/users"
    assert kwargs.source == {
        "type": "postgres",
        "table": "users",
        "connection": parse_database_url(TEST_DATABASE_URL),
    }
    assert "columns" not in kwargs.source

    assert kwargs.columns == [
        {
            "name": "user_id",
            "type": "integer",
            "description": "Unique identifier for the user",
        },
        {
            "name": "country",
            "type": "string",
            "description": "User country (groupable dimension)",
            "alias": "region",
        },
    ]
    assert all("group_by" not in column for column in kwargs.columns)


def test_users_model_uses_runtime_database_url_not_yaml_connection() -> None:
    users = load_semantic_models(FIXTURES_DIR).by_name()["users"]

    kwargs = to_pandasai_create_kwargs(users, database_url=TEST_DATABASE_URL)

    assert kwargs.source["connection"]["host"] == "db.example.com"
    assert kwargs.source["connection"]["user"] == "runtime_user"
    assert kwargs.source["connection"]["password"] == "runtime_pass"
    assert kwargs.source["connection"]["database"] == "runtime_db"
    assert users.source.connection.host == "localhost"
    assert users.source.connection.user == "test"


def test_subscriptions_model_normalizes_expression_and_join_hint() -> None:
    subscriptions = load_semantic_models(FIXTURES_DIR).by_name()["subscriptions"]
    kwargs = to_pandasai_create_kwargs(subscriptions, database_url=TEST_DATABASE_URL)

    assert kwargs.path == "public/subscriptions"
    assert "Join context:" in kwargs.description
    assert "user_id -> users.user_id" in kwargs.description
    assert "relations" not in kwargs.as_dict()
    assert "relationships" not in kwargs.as_dict()

    expression_column = kwargs.columns[-1]
    assert expression_column["name"] == "subscription_length_days"
    assert expression_column["expression"] == (
        "EXTRACT(DAY FROM (COALESCE(end_date, CURRENT_DATE) - start_date))"
    )
    assert "group_by" not in expression_column


def test_all_repo_models_map_without_error() -> None:
    result = load_semantic_models(REPO_MODELS_DIR)

    for model in result.models:
        kwargs = to_pandasai_create_kwargs(model, database_url=TEST_DATABASE_URL)
        assert kwargs.path == f"public/{model.name}"
        assert kwargs.source["connection"] == parse_database_url(TEST_DATABASE_URL)
        assert kwargs.columns
        assert all("group_by" not in column for column in kwargs.columns)
