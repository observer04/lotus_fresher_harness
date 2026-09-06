def create_customer(client, email="reservation@example.com"):
    response = client.post(
        "/customers",
        json={"name": "Reservation Guest", "email": email},
    )
    assert response.status_code == 201
    return response.get_json()


def test_a6_reservation_happy_path_and_read(client):
    customer = create_customer(client)
    created = client.post(
        "/reservations",
        json={
            "customer_id": customer["id"],
            "dining_table_id": 2,
            "reservation_time": "2030-02-01T19:00:00Z",
            "party_size": 2,
        },
    )
    assert created.status_code == 201
    reservation = created.get_json()
    assert reservation["status"] == "CONFIRMED"

    read = client.get(f"/reservations/{reservation['id']}")
    assert read.status_code == 200
    assert read.get_json() == reservation


def test_a6_party_too_large_is_rejected(client):
    customer = create_customer(client)
    response = client.post(
        "/reservations",
        json={
            "customer_id": customer["id"],
            "dining_table_id": 1,
            "reservation_time": "2030-02-02T19:00:00Z",
            "party_size": 3,
        },
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "PARTY_TOO_LARGE"


def test_a6_duplicate_table_time_is_rejected(client):
    customer = create_customer(client)
    payload = {
        "customer_id": customer["id"],
        "dining_table_id": 2,
        "reservation_time": "2030-02-03T20:00:00Z",
        "party_size": 2,
    }
    first = client.post("/reservations", json=payload)
    assert first.status_code == 201
    duplicate = client.post("/reservations", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "TABLE_ALREADY_RESERVED"
