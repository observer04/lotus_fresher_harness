def test_a5_create_customer_and_duplicate_email(client):
    payload = {
        "name": "Alice",
        "email": "alice@example.com",
        "phone": "+91-9000000011",
    }
    created = client.post("/customers", json=payload)
    assert created.status_code == 201
    assert created.get_json()["email"] == payload["email"]

    duplicate = client.post(
        "/customers",
        json={"name": "Other Alice", "email": "alice@example.com"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "DUPLICATE_EMAIL"
