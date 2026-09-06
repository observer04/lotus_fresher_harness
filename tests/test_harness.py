from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from harness.contract import ContractValidationError, OpenAPIContract
from harness.reset_db import reset_database
from harness.validate_openapi import validate_openapi_file

ROOT = Path(__file__).resolve().parents[1]


def test_a1_openapi_valid():
    spec = validate_openapi_file(ROOT / "openapi.yaml", require_library=True)
    operation_ids = {
        operation["operationId"]
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete", "options", "head"}
    }
    assert operation_ids == {
        "listMenu",
        "getMenuItem",
        "createCustomer",
        "listDiningTables",
        "createReservation",
        "getReservation",
        "createOrder",
        "getOrder",
        "updateOrderStatus",
        "listCustomerOrders",
    }


def test_a2_clean_db_is_deterministic(tmp_path: Path):
    db = tmp_path / "clean.sqlite3"
    reset_database(db, ROOT / "schema.sql", ROOT / "seed.sql")
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO customers(name, email) VALUES('Temporary', 'temporary@example.com')")
    conn.commit()
    conn.close()

    reset_database(db, ROOT / "schema.sql", ROOT / "seed.sql")
    conn = sqlite3.connect(db)
    try:
        customers = conn.execute("SELECT name, email FROM customers ORDER BY id").fetchall()
        menu_count = conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        active_tables = conn.execute("SELECT COUNT(*) FROM dining_tables WHERE active = 1").fetchone()[0]
    finally:
        conn.close()
    assert customers == [("Seed Guest", "seed@example.com")]
    assert menu_count == 4
    assert active_tables == 2


def test_a3_contract_judge_catches_intentionally_wrong_response(contract: OpenAPIContract):
    with pytest.raises(ContractValidationError) as excinfo:
        contract.validate_exchange(
            "GET",
            "/menu",
            None,
            200,
            {"wrong": "shape"},
        )
    message = str(excinfo.value)
    assert "listMenu" in message
    assert "response" in message


def test_contract_rejects_undeclared_status(contract: OpenAPIContract):
    with pytest.raises(ContractValidationError) as excinfo:
        contract.validate_exchange(
            "GET",
            "/menu/999",
            None,
            418,
            {"error": {"code": "TEAPOT", "message": "not in contract"}},
        )
    assert "getMenuItem" in str(excinfo.value)


def test_a12_harness_contains_no_restaurant_business_vocabulary():
    forbidden = {
        "menu_items",
        "menu_categories",
        "dining_tables",
        "reservations",
        "order_items",
        "party_size",
        "price_cents",
        "restaurantservice",
    }
    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted((ROOT / "harness").glob("*.py"))
    )
    hits = sorted(word for word in forbidden if word in source)
    assert hits == []
