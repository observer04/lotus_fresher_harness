from __future__ import annotations

from pathlib import Path

import pytest

from harness.contract import ContractClient, OpenAPIContract
from harness.reset_db import reset_database
from src.app import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "restaurant.sqlite3"
    reset_database(path, ROOT / "schema.sql", ROOT / "seed.sql")
    return path


@pytest.fixture
def app(db_path: Path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(db_path),
            # A1 separately checks the strict validator. Tests still start only
            # after basic OpenAPI validation and contract exchanges use openapi-core.
            "ALLOW_BASIC_SPEC_VALIDATION": True,
        }
    )


@pytest.fixture
def raw_client(app):
    return app.test_client()


@pytest.fixture
def contract() -> OpenAPIContract:
    return OpenAPIContract(ROOT / "openapi.yaml", require_openapi_core=True)


@pytest.fixture
def client(raw_client, contract):
    return ContractClient(raw_client, contract)
