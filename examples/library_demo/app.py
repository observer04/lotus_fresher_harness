from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, current_app, jsonify, request  # noqa: E402

from harness.validate_openapi import validate_openapi_file  # noqa: E402

OPENAPI_PATH = HERE / "openapi.yaml"


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_app(config: dict | None = None) -> Flask:
    require_validator = not (config or {}).get("ALLOW_BASIC_SPEC_VALIDATION", False)
    validate_openapi_file(OPENAPI_PATH, require_library=require_validator)

    app = Flask(__name__)
    app.config.from_mapping(DATABASE=str(HERE / "instance" / "library.sqlite3"))
    if config:
        app.config.update(config)

    @app.errorhandler(ApiProblem)
    def handle_problem(problem: ApiProblem):
        return jsonify({"error": {"code": problem.code, "message": problem.message}}), problem.status

    @app.get("/books")
    def list_books():
        conn = _connect(current_app.config["DATABASE"])
        try:
            rows = conn.execute(
                "SELECT id, title, author, available FROM books ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        return jsonify(
            {
                "books": [
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "author": row["author"],
                        "available": bool(row["available"]),
                    }
                    for row in rows
                ]
            }
        )

    @app.post("/loans")
    def create_loan():
        payload = request.get_json(silent=False)
        if not isinstance(payload, dict):
            raise ApiProblem(400, "BAD_REQUEST", "JSON object body required")
        book_id = payload.get("book_id")
        borrower = payload.get("borrower")
        if not isinstance(book_id, int) or not isinstance(borrower, str) or not borrower:
            raise ApiProblem(400, "BAD_REQUEST", "book_id and borrower are required")

        conn = _connect(current_app.config["DATABASE"])
        try:
            book = conn.execute(
                "SELECT id, available FROM books WHERE id = ?", (book_id,)
            ).fetchone()
            if book is None:
                raise ApiProblem(404, "BOOK_NOT_FOUND", "Book not found")
            if not book["available"]:
                raise ApiProblem(409, "BOOK_UNAVAILABLE", "Book is already on loan")
            cursor = conn.execute(
                "INSERT INTO loans (book_id, borrower, status) VALUES (?, ?, 'BORROWED')",
                (book_id, borrower),
            )
            conn.execute("UPDATE books SET available = 0 WHERE id = ?", (book_id,))
            conn.commit()
            loan_id = cursor.lastrowid
        finally:
            conn.close()
        return (
            jsonify({"id": loan_id, "book_id": book_id, "borrower": borrower, "status": "BORROWED"}),
            201,
        )

    @app.patch("/loans/<int:loan_id>/return")
    def return_loan(loan_id: int):
        conn = _connect(current_app.config["DATABASE"])
        try:
            loan = conn.execute(
                "SELECT id, book_id, borrower, status FROM loans WHERE id = ?", (loan_id,)
            ).fetchone()
            if loan is None:
                raise ApiProblem(404, "LOAN_NOT_FOUND", "Loan not found")
            if loan["status"] == "RETURNED":
                raise ApiProblem(409, "ALREADY_RETURNED", "Loan already returned")
            conn.execute("UPDATE loans SET status = 'RETURNED' WHERE id = ?", (loan_id,))
            conn.execute("UPDATE books SET available = 1 WHERE id = ?", (loan["book_id"],))
            conn.commit()
        finally:
            conn.close()
        return jsonify(
            {"id": loan_id, "book_id": loan["book_id"], "borrower": loan["borrower"], "status": "RETURNED"}
        )

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=5001, debug=False)
