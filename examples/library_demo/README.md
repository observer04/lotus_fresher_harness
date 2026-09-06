# Reusability proof: Library Lending API

This is a second, unrelated backend (books/loans instead of
menus/reservations/orders) that reuses `harness/` completely unmodified:

- `harness/validate_openapi.py` validates *this* `openapi.yaml`.
- `harness/reset_db.py` resets *this* `schema.sql` + `seed.sql` into a
  disposable SQLite file.
- `harness/contract.py` (`OpenAPIContract` + `ContractClient`) judges every
  HTTP request/response here against *this* contract.

None of those three files know books, loans, menus, or orders exist. Only
`app.py`, `openapi.yaml`, `schema.sql`, and `seed.sql` in this folder are
domain-specific — exactly the harness/implementation boundary the SOW
requires.

## Run it

```bash
source ../../.venv/bin/activate   # from repo root: source .venv/bin/activate
python examples/library_demo/demo.py
```

It validates the spec, resets the DB, borrows a book, proves a second loan on
the same book is rejected (409), returns it, and confirms it's available
again — with every exchange checked against `openapi.yaml` by the shared
harness.
