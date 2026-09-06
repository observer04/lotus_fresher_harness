from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import connect


@dataclass
class ApiProblem(Exception):
    status: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class RestaurantService:
    """Replaceable Restaurant business logic and parameterized SQLite access."""

    ALLOWED_TRANSITIONS = {
        "NEW": {"PREPARING", "CANCELLED"},
        "PREPARING": {"READY"},
        "READY": {"COMPLETED"},
        "COMPLETED": set(),
        "CANCELLED": set(),
    }

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def list_menu(self) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT c.id AS category_id, c.name AS category_name, c.sort_order,
                       m.id, m.name, m.description, m.price_cents, m.available
                  FROM menu_categories c
                  JOIN menu_items m ON m.category_id = c.id
                 WHERE m.available = 1
                 ORDER BY c.sort_order, c.id, m.id
                """
            ).fetchall()
        finally:
            conn.close()

        categories: list[dict[str, Any]] = []
        by_id: dict[int, dict[str, Any]] = {}
        for row in rows:
            category_id = int(row["category_id"])
            category = by_id.get(category_id)
            if category is None:
                category = {
                    "id": category_id,
                    "name": row["category_name"],
                    "items": [],
                }
                by_id[category_id] = category
                categories.append(category)
            category["items"].append(
                {
                    "id": int(row["id"]),
                    "category_id": category_id,
                    "name": row["name"],
                    "description": row["description"],
                    "price_cents": int(row["price_cents"]),
                    "available": bool(row["available"]),
                }
            )
        return {"categories": categories}

    def get_menu_item(self, item_id: int) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT id, category_id, name, description, price_cents, available
                  FROM menu_items WHERE id = ?
                """,
                (item_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise ApiProblem(404, "MENU_ITEM_NOT_FOUND", "Menu item not found")
        return {
            "id": int(row["id"]),
            "category_id": int(row["category_id"]),
            "name": row["name"],
            "description": row["description"],
            "price_cents": int(row["price_cents"]),
            "available": bool(row["available"]),
        }

    def create_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip()
        phone = payload.get("phone")
        if not name or not email:
            raise ApiProblem(400, "INVALID_CUSTOMER", "name and email are required")
        conn = connect(self.db_path)
        try:
            try:
                cur = conn.execute(
                    "INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
                    (name, email, phone),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                if "customers.email" in str(exc) or "UNIQUE constraint failed: customers.email" in str(exc):
                    raise ApiProblem(409, "DUPLICATE_EMAIL", "A customer with this email already exists") from exc
                raise
            row = conn.execute(
                "SELECT id, name, email, phone FROM customers WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def list_dining_tables(self) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT id, label, seats, active FROM dining_tables WHERE active = 1 ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        return {
            "tables": [
                {
                    "id": int(row["id"]),
                    "label": row["label"],
                    "seats": int(row["seats"]),
                    "active": bool(row["active"]),
                }
                for row in rows
            ]
        }

    def create_reservation(self, payload: dict[str, Any]) -> dict[str, Any]:
        customer_id = payload.get("customer_id")
        table_id = payload.get("dining_table_id")
        reservation_time = str(payload.get("reservation_time", "")).strip()
        party_size = payload.get("party_size")
        if not isinstance(customer_id, int) or not isinstance(table_id, int) or not reservation_time:
            raise ApiProblem(400, "INVALID_RESERVATION", "customer_id, dining_table_id and reservation_time are required")
        if not isinstance(party_size, int) or party_size <= 0:
            raise ApiProblem(422, "INVALID_PARTY_SIZE", "party_size must be greater than zero")

        conn = connect(self.db_path)
        try:
            customer = conn.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
            if customer is None:
                raise ApiProblem(404, "CUSTOMER_NOT_FOUND", "Customer not found")
            table = conn.execute(
                "SELECT id, seats, active FROM dining_tables WHERE id = ?", (table_id,)
            ).fetchone()
            if table is None or not bool(table["active"]):
                raise ApiProblem(404, "TABLE_NOT_FOUND", "Active dining table not found")
            if party_size > int(table["seats"]):
                raise ApiProblem(422, "PARTY_TOO_LARGE", "party_size exceeds selected table seats")
            duplicate = conn.execute(
                """
                SELECT id FROM reservations
                 WHERE dining_table_id = ? AND reservation_time = ? AND status = 'CONFIRMED'
                """,
                (table_id, reservation_time),
            ).fetchone()
            if duplicate is not None:
                raise ApiProblem(409, "TABLE_ALREADY_RESERVED", "Dining table is already reserved for that time")
            try:
                cur = conn.execute(
                    """
                    INSERT INTO reservations
                        (customer_id, dining_table_id, reservation_time, party_size, status)
                    VALUES (?, ?, ?, ?, 'CONFIRMED')
                    """,
                    (customer_id, table_id, reservation_time, party_size),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                if "reservations.dining_table_id, reservations.reservation_time" in str(exc):
                    raise ApiProblem(409, "TABLE_ALREADY_RESERVED", "Dining table is already reserved for that time") from exc
                raise
            row = conn.execute(
                """
                SELECT id, customer_id, dining_table_id, reservation_time, party_size, status
                  FROM reservations WHERE id = ?
                """,
                (cur.lastrowid,),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def get_reservation(self, reservation_id: int) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT id, customer_id, dining_table_id, reservation_time, party_size, status
                  FROM reservations WHERE id = ?
                """,
                (reservation_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise ApiProblem(404, "RESERVATION_NOT_FOUND", "Reservation not found")
        return dict(row)

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        customer_id = payload.get("customer_id")
        table_id = payload.get("dining_table_id")
        reservation_id = payload.get("reservation_id")
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ApiProblem(400, "INVALID_ORDER", "items must contain at least one order line")

        conn = connect(self.db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_optional_fk(conn, "customers", customer_id, "CUSTOMER_NOT_FOUND", "Customer not found")
            self._ensure_optional_fk(conn, "dining_tables", table_id, "TABLE_NOT_FOUND", "Dining table not found")
            self._ensure_optional_fk(conn, "reservations", reservation_id, "RESERVATION_NOT_FOUND", "Reservation not found")

            cur = conn.execute(
                """
                INSERT INTO orders (customer_id, dining_table_id, reservation_id, status, total_cents)
                VALUES (?, ?, ?, 'NEW', 0)
                """,
                (customer_id, table_id, reservation_id),
            )
            order_id = int(cur.lastrowid)
            total_cents = 0
            for line in items:
                if not isinstance(line, dict):
                    raise ApiProblem(400, "INVALID_ORDER_ITEM", "Each order item must be an object")
                menu_item_id = line.get("menu_item_id")
                quantity = line.get("quantity")
                if not isinstance(menu_item_id, int) or not isinstance(quantity, int) or quantity <= 0:
                    raise ApiProblem(422, "INVALID_ORDER_ITEM", "menu_item_id must be an integer and quantity must be greater than zero")
                menu_row = conn.execute(
                    "SELECT id, price_cents, available FROM menu_items WHERE id = ?",
                    (menu_item_id,),
                ).fetchone()
                if menu_row is None:
                    raise ApiProblem(404, "MENU_ITEM_NOT_FOUND", f"Menu item {menu_item_id} not found")
                if not bool(menu_row["available"]):
                    raise ApiProblem(422, "MENU_ITEM_UNAVAILABLE", f"Menu item {menu_item_id} is unavailable")
                unit_price = int(menu_row["price_cents"])
                line_total = quantity * unit_price
                total_cents += line_total
                conn.execute(
                    """
                    INSERT INTO order_items
                        (order_id, menu_item_id, quantity, unit_price_cents, line_total_cents)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (order_id, menu_item_id, quantity, unit_price, line_total),
                )
            conn.execute("UPDATE orders SET total_cents = ? WHERE id = ?", (total_cents, order_id))
            conn.commit()
        except ApiProblem:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_order(order_id)

    @staticmethod
    def _ensure_optional_fk(
        conn: sqlite3.Connection,
        table_name: str,
        value: Any,
        code: str,
        message: str,
    ) -> None:
        if value is None:
            return
        if not isinstance(value, int):
            raise ApiProblem(400, "INVALID_REFERENCE", f"{table_name} reference must be an integer")
        # table_name is selected only from fixed internal constants above, never from caller data.
        row = conn.execute(f"SELECT id FROM {table_name} WHERE id = ?", (value,)).fetchone()
        if row is None:
            raise ApiProblem(404, code, message)

    def get_order(self, order_id: int) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            order = conn.execute(
                """
                SELECT id, customer_id, dining_table_id, reservation_id, status, total_cents, created_at
                  FROM orders WHERE id = ?
                """,
                (order_id,),
            ).fetchone()
            if order is None:
                raise ApiProblem(404, "ORDER_NOT_FOUND", "Order not found")
            item_rows = conn.execute(
                """
                SELECT oi.id, oi.menu_item_id, mi.name AS menu_item_name, oi.quantity,
                       oi.unit_price_cents, oi.line_total_cents
                  FROM order_items oi
                  JOIN menu_items mi ON mi.id = oi.menu_item_id
                 WHERE oi.order_id = ?
                 ORDER BY oi.id
                """,
                (order_id,),
            ).fetchall()
        finally:
            conn.close()
        result = dict(order)
        result["items"] = [dict(row) for row in item_rows]
        return result

    def update_order_status(self, order_id: int, new_status: str) -> dict[str, Any]:
        if new_status not in self.ALLOWED_TRANSITIONS:
            raise ApiProblem(422, "INVALID_ORDER_STATUS", "Unknown order status")
        conn = connect(self.db_path)
        try:
            row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row is None:
                raise ApiProblem(404, "ORDER_NOT_FOUND", "Order not found")
            current = str(row["status"])
            if new_status not in self.ALLOWED_TRANSITIONS[current]:
                raise ApiProblem(
                    409,
                    "INVALID_STATUS_TRANSITION",
                    f"Transition {current} -> {new_status} is not allowed",
                )
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
            conn.commit()
        finally:
            conn.close()
        return self.get_order(order_id)

    def list_customer_orders(self, customer_id: int) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            exists = conn.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
            if exists is None:
                raise ApiProblem(404, "CUSTOMER_NOT_FOUND", "Customer not found")
            ids = [
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM orders WHERE customer_id = ? ORDER BY id", (customer_id,)
                ).fetchall()
            ]
        finally:
            conn.close()
        return {"orders": [self.get_order(order_id) for order_id in ids]}
