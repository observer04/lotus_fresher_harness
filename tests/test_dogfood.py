def test_a13_canonical_fresher_workflow(client):
    menu = client.get("/menu").get_json()
    menu_ids = [item["id"] for category in menu["categories"] for item in category["items"]]

    alice_response = client.post(
        "/customers",
        json={"name": "Alice", "email": "alice.dogfood@example.com"},
    )
    assert alice_response.status_code == 201
    alice = alice_response.get_json()

    tables = client.get("/tables").get_json()["tables"]
    table = next(table for table in tables if table["seats"] == 4)

    reservation_response = client.post(
        "/reservations",
        json={
            "customer_id": alice["id"],
            "dining_table_id": table["id"],
            "reservation_time": "2030-03-01T19:30:00Z",
            "party_size": 2,
        },
    )
    assert reservation_response.status_code == 201
    reservation = reservation_response.get_json()

    order_response = client.post(
        "/orders",
        json={
            "customer_id": alice["id"],
            "dining_table_id": table["id"],
            "reservation_id": reservation["id"],
            "items": [
                {"menu_item_id": menu_ids[0], "quantity": 1},
                {"menu_item_id": menu_ids[1], "quantity": 1},
            ],
        },
    )
    assert order_response.status_code == 201
    order = order_response.get_json()

    read = client.get(f"/orders/{order['id']}")
    assert read.status_code == 200
    assert read.get_json()["total_cents"] == sum(
        item["quantity"] * item["unit_price_cents"] for item in read.get_json()["items"]
    )

    for state in ("PREPARING", "READY", "COMPLETED"):
        response = client.patch(
            f"/orders/{order['id']}/status",
            json={"status": state},
        )
        assert response.status_code == 200

    history = client.get(f"/customers/{alice['id']}/orders")
    assert history.status_code == 200
    assert any(
        item["id"] == order["id"] and item["status"] == "COMPLETED"
        for item in history.get_json()["orders"]
    )
