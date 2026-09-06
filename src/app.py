from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request

from harness.validate_openapi import validate_openapi_file
from .handlers import ApiProblem, RestaurantService

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "openapi.yaml"

SWAGGER_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Restaurant API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
window.onload = () => SwaggerUIBundle({ url: '/openapi.yaml', dom_id: '#swagger-ui' });
</script>
</body>
</html>
"""


def create_app(config: dict | None = None) -> Flask:
    # The contract is checked before endpoint registration/application use.
    require_validator = not (config or {}).get("ALLOW_BASIC_SPEC_VALIDATION", False)
    validate_openapi_file(OPENAPI_PATH, require_library=require_validator)

    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("RESTAURANT_DB", str(ROOT / "instance" / "restaurant.sqlite3")),
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)

    def service() -> RestaurantService:
        return RestaurantService(current_app.config["DATABASE"])

    @app.errorhandler(ApiProblem)
    def handle_problem(problem: ApiProblem):
        return jsonify({"error": {"code": problem.code, "message": problem.message}}), problem.status

    @app.errorhandler(400)
    def handle_bad_request(_error):
        return jsonify({"error": {"code": "BAD_REQUEST", "message": "Malformed request"}}), 400

    @app.get("/menu")
    def list_menu():
        return jsonify(service().list_menu())

    @app.get("/menu/<int:item_id>")
    def get_menu_item(item_id: int):
        return jsonify(service().get_menu_item(item_id))

    @app.post("/customers")
    def create_customer():
        return jsonify(service().create_customer(_json_object())), 201

    @app.get("/tables")
    def list_tables():
        return jsonify(service().list_dining_tables())

    @app.post("/reservations")
    def create_reservation():
        return jsonify(service().create_reservation(_json_object())), 201

    @app.get("/reservations/<int:reservation_id>")
    def get_reservation(reservation_id: int):
        return jsonify(service().get_reservation(reservation_id))

    @app.post("/orders")
    def create_order():
        return jsonify(service().create_order(_json_object())), 201

    @app.get("/orders/<int:order_id>")
    def get_order(order_id: int):
        return jsonify(service().get_order(order_id))

    @app.patch("/orders/<int:order_id>/status")
    def update_order_status(order_id: int):
        payload = _json_object()
        status = payload.get("status")
        if not isinstance(status, str):
            raise ApiProblem(400, "INVALID_ORDER_STATUS", "status is required")
        return jsonify(service().update_order_status(order_id, status))

    @app.get("/customers/<int:customer_id>/orders")
    def list_customer_orders(customer_id: int):
        return jsonify(service().list_customer_orders(customer_id))

    @app.get("/openapi.yaml")
    def openapi_document():
        return Response(OPENAPI_PATH.read_text(encoding="utf-8"), mimetype="application/yaml")

    @app.get("/docs")
    def docs():
        return Response(SWAGGER_HTML, mimetype="text/html")

    return app


def _json_object() -> dict:
    payload = request.get_json(silent=False)
    if not isinstance(payload, dict):
        raise ApiProblem(400, "BAD_REQUEST", "JSON object body required")
    return payload


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
