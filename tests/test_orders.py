from __future__ import annotations

import sqlite3


def create_customer(client, email="orders@example.com"):
    response = client.post("/customers", json={"name": "Order Guest", "email": email})
    assert response.status_code == 201
    return response.get_json()


def create_basic_order(client, customer_id: int):
    response = client.post(
        "/orders",
        json={
            "customer_id": customer_id,
            "items": [
                {"menu_item_id": 1, "quantity": 2},
                {"menu_item_id": 2, "quantity": 1},
            ],
        },
    )
    assert response.status_code == 201
    return response.get_json()


def test_a7_order_transaction_and_server_owned_prices(client, db_path):
    customer = create_customer(client)
    order = create_basic_order(client, customer["id"])

    assert order["total_cents"] == 2 * 450 + 850
    assert [line["unit_price_cents"] for line in order["items"]] == [450, 850]
    assert sum(line["line_total_cents"] for line in order["items"]) == order["total_cents"]

    # The request contract has no client price field. Defense-in-depth: even an
    # out-of-contract raw request that supplies fake prices is ignored by the backend.
    conn = sqlite3.connect(db_path)
    before = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    assert before == 1


def test_server_ignores_out_of_contract_price_fields(raw_client, db_path):
    response = raw_client.post(
        "/orders",
        json={
            "customer_id": 1,
            "items": [
                {
                    "menu_item_id": 1,
                    "quantity": 2,
                    "unit_price_cents": 1,
                    "line_total_cents": 2,
                }
            ],
        },
    )
    assert response.status_code == 201
    order = response.get_json()
    assert order["total_cents"] == 900
    assert order["items"][0]["unit_price_cents"] == 450
    assert order["items"][0]["line_total_cents"] == 900


def test_a7_unavailable_item_rolls_back_entire_order(client, db_path):
    customer = create_customer(client)
    conn = sqlite3.connect(db_path)
    before_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    before_lines = conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    conn.close()

    response = client.post(
        "/orders",
        json={
            "customer_id": customer["id"],
            "items": [
                {"menu_item_id": 1, "quantity": 1},
                {"menu_item_id": 4, "quantity": 1},
            ],
        },
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "MENU_ITEM_UNAVAILABLE"

    conn = sqlite3.connect(db_path)
    after_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    after_lines = conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    conn.close()
    assert after_orders == before_orders
    assert after_lines == before_lines


def test_a8_get_order_returns_joined_item_details(client):
    customer = create_customer(client)
    created = create_basic_order(client, customer["id"])
    response = client.get(f"/orders/{created['id']}")
    assert response.status_code == 200
    order = response.get_json()
    assert order["id"] == created["id"]
    assert order["items"][0]["menu_item_name"] == "Tomato Soup"
    assert order["items"][1]["menu_item_name"] == "Paneer Tikka"


def test_historical_order_item_price_is_preserved(client, db_path):
    customer = create_customer(client)
    order = create_basic_order(client, customer["id"])

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE menu_items SET price_cents = 9999 WHERE id = 1")
    conn.commit()
    conn.close()

    read = client.get(f"/orders/{order['id']}")
    assert read.status_code == 200
    tomato_line = next(line for line in read.get_json()["items"] if line["menu_item_id"] == 1)
    assert tomato_line["unit_price_cents"] == 450


def test_a9_order_state_machine(client):
    customer = create_customer(client)
    order = create_basic_order(client, customer["id"])

    invalid = client.patch(f"/orders/{order['id']}/status", json={"status": "READY"})
    assert invalid.status_code == 409
    assert invalid.get_json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    for expected in ("PREPARING", "READY", "COMPLETED"):
        response = client.patch(
            f"/orders/{order['id']}/status",
            json={"status": expected},
        )
        assert response.status_code == 200
        assert response.get_json()["status"] == expected

    terminal = client.patch(
        f"/orders/{order['id']}/status",
        json={"status": "CANCELLED"},
    )
    assert terminal.status_code == 409


def test_new_order_can_be_cancelled(client):
    customer = create_customer(client)
    order = create_basic_order(client, customer["id"])
    response = client.patch(
        f"/orders/{order['id']}/status",
        json={"status": "CANCELLED"},
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "CANCELLED"


def test_a10_customer_order_history(client):
    customer = create_customer(client)
    first = create_basic_order(client, customer["id"])
    second = client.post(
        "/orders",
        json={
            "customer_id": customer["id"],
            "items": [{"menu_item_id": 3, "quantity": 2}],
        },
    )
    assert second.status_code == 201

    history = client.get(f"/customers/{customer['id']}/orders")
    assert history.status_code == 200
    ids = [order["id"] for order in history.get_json()["orders"]]
    assert ids == [first["id"], second.get_json()["id"]]
