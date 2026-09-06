from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def reset_database(db_path: str | Path, schema_path: str | Path, seed_path: str | Path) -> Path:
    db = Path(db_path)
    schema = Path(schema_path)
    seed = Path(seed_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema.read_text(encoding="utf-8"))
        conn.executescript(seed.read_text(encoding="utf-8"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return db


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a disposable SQLite database from schema + seed SQL")
    parser.add_argument("--db", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--seed", required=True)
    args = parser.parse_args()
    path = reset_database(args.db, args.schema, args.seed)
    print(f"PASS clean SQLite database: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
