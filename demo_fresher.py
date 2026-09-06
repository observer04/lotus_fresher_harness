from __future__ import annotations

import argparse
import sys
from typing import Any

import requests


class DemoFailure(RuntimeError):
    pass


def call(base: str, method: str, path: str, *, json: Any = None, expected: int = 200):
    response = requests.request(method, base + path, json=json, timeout=5)
    try:
        body = response.json()
    except Exception:
        body = response.text
    if response.status_code != expected:
        raise DemoFailure(
            f"{method} {path}: expected {expected}, got {response.status_code}: {body}"
        )
    return body


def step(number: str, label: str, fn):
    print(f"[{number}] {label}")
    result = fn()
    print("      PASS")
    return result


def run(base: str, negative: bool) -> None:
    print("FRESHER RESTAURANT DOGFOOD DEMO\n")

    menu = step("1/9", "GET /menu", lambda: call(base, "GET", "/menu"))
    available_ids = [
        item["id"]
        for category in menu["categories"]
        for item in category["items"]
    ]
    if len(available_ids) < 2:
        raise DemoFailure("Need at least two available menu items")

    alice = step(
        "2/9",
        "POST /customers - create Alice",
        lambda: call(
            base,
            "POST",
            "/customers",
            json={
                "name": "Alice",
                "email": "alice.demo@example.com",
                "phone": "+91-9000000001",
            },
            expected=201,
        ),
    )

    tables = step(
        "3/9",
        "GET /tables - choose a 4-seat table",
        lambda: call(base, "GET", "/tables"),
    )
    table = next((t for t in tables["tables"] if t["seats"] >= 4), None)
    if table is None:
        raise DemoFailure("No active 4-seat table available")

    reservation = step(
        "4/9",
        "POST /reservations - Alice, party of 2",
        lambda: call(
            base,
            "POST",
            "/reservations",
            json={
                "customer_id": alice["id"],
                "dining_table_id": table["id"],
                "reservation_time": "2030-01-15T19:30:00Z",
                "party_size": 2,
            },
            expected=201,
        ),
    )

    order = step(
        "5/9",
        "POST /orders - Alice orders 2 menu items",
        lambda: call(
            base,
            "POST",
            "/orders",
            json={
                "customer_id": alice["id"],
                "dining_table_id": table["id"],
                "reservation_id": reservation["id"],
                "items": [
                    {"menu_item_id": available_ids[0], "quantity": 1},
                    {"menu_item_id": available_ids[1], "quantity": 1},
                ],
            },
            expected=201,
        ),
    )
    print(f"      server total = {order['total_cents']} cents")

    read_order = step(
        "6/9",
        f"GET /orders/{order['id']} - verify total",
        lambda: call(base, "GET", f"/orders/{order['id']}"),
    )
    computed = sum(
        line["quantity"] * line["unit_price_cents"] for line in read_order["items"]
    )
    if computed != read_order["total_cents"]:
        raise DemoFailure("Server total does not equal persisted line totals")

    step(
        "7/9",
        "PATCH NEW -> PREPARING",
        lambda: call(
            base,
            "PATCH",
            f"/orders/{order['id']}/status",
            json={"status": "PREPARING"},
        ),
    )

    step(
        "8/9",
        "PATCH PREPARING -> READY -> COMPLETED",
        lambda: (
            call(
                base,
                "PATCH",
                f"/orders/{order['id']}/status",
                json={"status": "READY"},
            ),
            call(
                base,
                "PATCH",
                f"/orders/{order['id']}/status",
                json={"status": "COMPLETED"},
            ),
        ),
    )

    history = step(
        "9/9",
        f"GET /customers/{alice['id']}/orders - verify completed order",
        lambda: call(base, "GET", f"/customers/{alice['id']}/orders"),
    )
    if not any(
        item["id"] == order["id"] and item["status"] == "COMPLETED"
        for item in history["orders"]
    ):
        raise DemoFailure("Completed order is missing from customer history")

    if negative:
        print("\nNEGATIVE BUSINESS-RULE PROOFS")
        checks = [
            (
                "duplicate email rejected",
                lambda: call(
                    base,
                    "POST",
                    "/customers",
                    json={
                        "name": "Alice Again",
                        "email": "alice.demo@example.com",
                    },
                    expected=409,
                ),
            ),
            (
                "oversized reservation rejected",
                lambda: call(
                    base,
                    "POST",
                    "/reservations",
                    json={
                        "customer_id": alice["id"],
                        "dining_table_id": table["id"],
                        "reservation_time": "2030-01-16T19:30:00Z",
                        "party_size": table["seats"] + 1,
                    },
                    expected=422,
                ),
            ),
            (
                "duplicate table/time rejected",
                lambda: call(
                    base,
                    "POST",
                    "/reservations",
                    json={
                        "customer_id": alice["id"],
                        "dining_table_id": table["id"],
                        "reservation_time": "2030-01-15T19:30:00Z",
                        "party_size": 2,
                    },
                    expected=409,
                ),
            ),
        ]
        for label, fn in checks:
            fn()
            print(f"  PASS - {label}")

    print("\nDOGFOOD FLOW: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the canonical second-Fresher workflow over HTTP"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument(
        "--negative",
        action="store_true",
        help="also prove selected expected failures",
    )
    args = parser.parse_args()
    try:
        run(args.base_url.rstrip("/"), args.negative)
    except (requests.RequestException, DemoFailure) as exc:
        print(f"DOGFOOD FLOW: FAIL - {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
