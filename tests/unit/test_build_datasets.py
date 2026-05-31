from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from talk_to_data_slackbot.pandas_ai.analytics import (
    EXPECTED_DATASET_NAMES,
    DatasetRegistrationError,
    build_datasets,
    build_registration_plans,
    compute_registration_fingerprint,
    to_pandasai_create_kwargs,
)
from talk_to_data_slackbot.pandas_ai.semantic_loader import load_semantic_models

REPO_MODELS_DIR = Path(__file__).resolve().parents[2] / "semantic_models"
TEST_DATABASE_URL = "postgresql://runtime_user:runtime_pass@db.example.com:5433/runtime_db"


def test_build_registration_plans_for_all_repo_models() -> None:
    plans = build_registration_plans(
        database_url=TEST_DATABASE_URL,
        models_dir=REPO_MODELS_DIR,
    )

    assert len(plans) == 4
    assert [plan.path for plan in plans] == [
        "public/payments",
        "public/sessions",
        "public/subscriptions",
        "public/users",
    ]
    assert frozenset(_dataset_name(plan) for plan in plans) == EXPECTED_DATASET_NAMES
    assert all(plan.fingerprint for plan in plans)
    assert all(plan.create_kwargs.columns for plan in plans)


def test_registration_fingerprint_is_stable_for_same_adapter_output() -> None:
    users = load_semantic_models(REPO_MODELS_DIR).by_name()["users"]
    kwargs = to_pandasai_create_kwargs(users, database_url=TEST_DATABASE_URL)

    first = compute_registration_fingerprint(kwargs)
    second = compute_registration_fingerprint(kwargs)

    assert first == second


def test_registration_fingerprint_changes_when_database_url_changes() -> None:
    users = load_semantic_models(REPO_MODELS_DIR).by_name()["users"]
    first = compute_registration_fingerprint(
        to_pandasai_create_kwargs(
            users,
            database_url="postgresql://a:a@host-a:5432/db_a",
        )
    )
    second = compute_registration_fingerprint(
        to_pandasai_create_kwargs(
            users,
            database_url="postgresql://b:b@host-b:5432/db_b",
        )
    )

    assert first != second


@patch("talk_to_data_slackbot.pandas_ai.analytics.pai.load")
@patch("talk_to_data_slackbot.pandas_ai.analytics.pai.create")
def test_build_datasets_creates_all_four_when_cache_missing(
    mock_create: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    mock_create.side_effect = lambda **_: MagicMock(name="created-dataset")

    datasets = build_datasets(
        database_url=TEST_DATABASE_URL,
        models_dir=REPO_MODELS_DIR,
        datasets_root=tmp_path,
    )

    assert len(datasets) == 4
    assert mock_load.call_count == 0
    assert mock_create.call_count == 4
    created_paths = [call_.kwargs["path"] for call_ in mock_create.call_args_list]
    assert created_paths == [
        "public/payments",
        "public/sessions",
        "public/subscriptions",
        "public/users",
    ]
    for call_ in mock_create.call_args_list:
        assert "columns" in call_.kwargs
        assert "source" in call_.kwargs
        assert "columns" not in call_.kwargs["source"]


@patch("talk_to_data_slackbot.pandas_ai.analytics.pai.load")
@patch("talk_to_data_slackbot.pandas_ai.analytics.pai.create")
def test_build_datasets_loads_when_fingerprint_matches(
    mock_create: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    plans = build_registration_plans(
        database_url=TEST_DATABASE_URL,
        models_dir=REPO_MODELS_DIR,
    )
    for plan in plans:
        cache_dir = tmp_path.joinpath(*plan.path.split("/"))
        cache_dir.mkdir(parents=True)
        (cache_dir / "schema.yaml").write_text("name: placeholder\n", encoding="utf-8")
        (cache_dir / ".registration_fingerprint").write_text(
            plan.fingerprint,
            encoding="utf-8",
        )

    mock_load.side_effect = lambda path: MagicMock(name=f"loaded:{path}")

    datasets = build_datasets(
        database_url=TEST_DATABASE_URL,
        models_dir=REPO_MODELS_DIR,
        datasets_root=tmp_path,
    )

    assert len(datasets) == 4
    assert mock_create.call_count == 0
    assert mock_load.call_count == 4
    assert mock_load.call_args_list == [
        call("public/payments"),
        call("public/sessions"),
        call("public/subscriptions"),
        call("public/users"),
    ]


@patch("talk_to_data_slackbot.pandas_ai.analytics.pai.load")
@patch("talk_to_data_slackbot.pandas_ai.analytics.pai.create")
def test_build_datasets_recreates_when_fingerprint_changes(
    mock_create: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    plans = build_registration_plans(
        database_url=TEST_DATABASE_URL,
        models_dir=REPO_MODELS_DIR,
    )
    for plan in plans:
        cache_dir = tmp_path.joinpath(*plan.path.split("/"))
        cache_dir.mkdir(parents=True)
        (cache_dir / "schema.yaml").write_text("name: stale\n", encoding="utf-8")
        (cache_dir / ".registration_fingerprint").write_text(
            "stale-fingerprint",
            encoding="utf-8",
        )

    mock_create.side_effect = lambda **_: MagicMock(name="recreated-dataset")

    build_datasets(
        database_url=TEST_DATABASE_URL,
        models_dir=REPO_MODELS_DIR,
        datasets_root=tmp_path,
    )

    assert mock_load.call_count == 0
    assert mock_create.call_count == 4
    for plan in plans:
        cache_dir = tmp_path.joinpath(*plan.path.split("/"))
        assert (
            cache_dir / ".registration_fingerprint"
        ).read_text(encoding="utf-8") == plan.fingerprint


def test_build_datasets_raises_when_expected_models_missing(
    tmp_path: Path,
) -> None:
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "semantic_models" / "valid"

    with pytest.raises(DatasetRegistrationError, match="missing:"):
        build_datasets(
            database_url=TEST_DATABASE_URL,
            models_dir=fixtures_dir,
            datasets_root=tmp_path,
        )


def _dataset_name(plan: object) -> str:
    return getattr(plan, "path").split("/", 1)[1]
