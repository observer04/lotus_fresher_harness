"""Proof that harness/ is reusable: a second, unrelated domain judged by the
exact same harness modules used for the Restaurant backend, unmodified.

Run from the repo root:
    python examples/library_demo/demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness.contract import ContractClient, OpenAPIContract  # noqa: E402
from harness.reset_db import reset_database  # noqa: E402
from harness.validate_openapi import validate_openapi_file  # noqa: E402

from app import create_app  # noqa: E402


def main() -> int:
    db_path = HERE / "instance" / "library.sqlite3"
    schema_path = HERE / "schema.sql"
    seed_path = HERE / "seed.sql"
    openapi_path = HERE / "openapi.yaml"

    print("PROVING HARNESS REUSE: Library Lending API")
    print("(different domain, same harness/ package, zero lines changed)\n")

    validate_openapi_file(openapi_path, require_library=True)
    print("[harness.validate_openapi] PASS - library openapi.yaml is valid")

    reset_database(db_path, schema_path, seed_path)
    print("[harness.reset_db]         PASS - fresh library.sqlite3 from schema.sql + seed.sql\n")

    app = create_app({"TESTING": True, "DATABASE": str(db_path)})
    raw_client = app.test_client()
    contract = OpenAPIContract(openapi_path, require_openapi_core=True)
    client = ContractClient(raw_client, contract)

    results: list[tuple[str, bool]] = []

    def check(label: str, condition: bool) -> None:
        results.append((label, condition))
        print(f"  {'PASS' if condition else 'FAIL'} - {label}")
        if not condition:
            raise SystemExit(1)

    resp = client.get("/books")
    books = resp.get_json()["books"]
    check("GET /books", resp.status_code == 200 and len(books) == 3)
    book_id = books[0]["id"]

    resp = client.post("/loans", json={"book_id": book_id, "borrower": "Alice"})
    loan = resp.get_json()
    check("POST /loans - Alice borrows a book", resp.status_code == 201)

    resp = client.post("/loans", json={"book_id": book_id, "borrower": "Bob"})
    check(
        "POST /loans - duplicate borrow of same book rejected (409)",
        resp.status_code == 409,
    )

    resp = client.patch(f"/loans/{loan['id']}/return", json=None)
    check(
        "PATCH /loans/{id}/return",
        resp.status_code == 200 and resp.get_json()["status"] == "RETURNED",
    )

    resp = client.get("/books")
    check(
        "GET /books - book available again after return",
        resp.get_json()["books"][0]["available"] is True,
    )

    print("\nEvery request/response above was validated against")
    print(f"  {openapi_path.relative_to(ROOT)}")
    print("by the unmodified harness modules:")
    print("  harness/validate_openapi.py")
    print("  harness/reset_db.py")
    print("  harness/contract.py  (OpenAPIContract + ContractClient)")
    print("\nDEMO: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
