def test_a4_menu_returns_only_available_items(client):
    response = client.get("/menu")
    assert response.status_code == 200
    body = response.get_json()
    items = [item for category in body["categories"] for item in category["items"]]
    assert items
    assert all(item["available"] is True for item in items)
    assert {item["id"] for item in items} == {1, 2, 3}


def test_get_menu_item_and_404(client):
    response = client.get("/menu/1")
    assert response.status_code == 200
    assert response.get_json()["name"] == "Tomato Soup"

    missing = client.get("/menu/999")
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "MENU_ITEM_NOT_FOUND"


def test_list_tables_returns_active_only(client):
    response = client.get("/tables")
    assert response.status_code == 200
    tables = response.get_json()["tables"]
    assert {table["label"] for table in tables} == {"T1", "T2"}
    assert all(table["active"] is True for table in tables)
