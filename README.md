# Restaurant OpenAPI + SQLite Harness

This repository contains two deliberately separate parts:

1. **Reusable harness** in `harness/`: OpenAPI validation, disposable SQLite reset, HTTP request/response contract judging, and common test-client support. It contains no Restaurant table/menu/order business logic.
2. **Restaurant reference backend** in `src/` plus `schema.sql`, `seed.sql`, `openapi.yaml`, and Restaurant-specific tests. It proves that the harness can judge a concrete implementation.

`openapi.yaml` is the interface contract and source of truth.

Status: all acceptance tests in `ACCEPTANCE.md` (A1-A13) pass; `./run-tests.sh` runs clean
twice in a row from a fresh SQLite database.

## Requirements

- Python 3.10+
- No external database or credentials

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Validate the contract

```bash
python -m harness.validate_openapi openapi.yaml --strict
```

The application also validates `openapi.yaml` before it starts.

## Reset the SQLite database

```bash
python -m harness.reset_db \
  --db instance/restaurant.sqlite3 \
  --schema schema.sql \
  --seed seed.sql
```

The DB is disposable. Resetting deletes and recreates it from `schema.sql` + `seed.sql`.

## Run the service

```bash
make run
```

The service starts at `http://127.0.0.1:5000`.

- Swagger UI: `http://127.0.0.1:5000/docs`
- Raw OpenAPI contract: `http://127.0.0.1:5000/openapi.yaml`

Swagger UI loads its static assets from the public unpkg CDN. The API itself has no external runtime dependency.

## Run the complete harness

```bash
make test
# or
./run-tests.sh
```

`run-tests.sh` validates the OpenAPI document, then runs the full pytest suite **twice**. Every pytest test uses a fresh temporary SQLite file.

Contract-aware tests use `ContractClient`: it calls the Flask HTTP interface, then validates the request and returned status/body against `openapi.yaml`. With installed requirements it uses `openapi-core`; a small generic JSON-Schema fallback is retained only to make contract failures readable when the core package is unavailable during development.

## Canonical second-Fresher / dogfood test

This is a human usability proof, not a second software component.

1. Start clean: `make run` (this validates and resets the DB).
2. Open `/docs`.
3. Without reading `src/`, perform this flow from Swagger:
   - `GET /menu`
   - `POST /customers` to create Alice
   - `GET /tables` and choose a 4-seat table
   - `POST /reservations` for Alice, party of 2
   - `POST /orders` with two menu items
   - `GET /orders/{id}` and verify the server total
   - `PATCH /orders/{id}/status` through `NEW -> PREPARING -> READY -> COMPLETED`
   - `GET /customers/{id}/orders` and verify the completed order
4. Run `make test`.

For a deterministic recorded demo, start the server from a clean DB and run in another terminal:

```bash
python demo_fresher.py --negative
```

The script uses real HTTP requests and prints PASS/FAIL for the canonical sequence plus selected expected business-rule failures.

## Business rules implemented

- Menu prices and order totals are owned by SQLite/backend code, never by the caller.
- Order creation and all `order_items` inserts are one transaction.
- Unavailable menu items cannot be ordered.
- `party_size` must be positive and fit the selected active table.
- A table cannot have two confirmed reservations at the same `reservation_time`.
- Statuses: `NEW`, `PREPARING`, `READY`, `COMPLETED`, `CANCELLED`.
- Transitions: `NEW -> PREPARING|CANCELLED`, `PREPARING -> READY`, `READY -> COMPLETED` only.
- `order_items.unit_price_cents` is copied from the menu at order time, so later menu-price changes do not rewrite history.

## Inspect / add an endpoint

1. Add or change the operation in `openapi.yaml` first, including `operationId`, request schema, response status codes, and response schema.
2. Run `make validate`.
3. Implement the route in `src/app.py` and Restaurant logic/SQL in `src/handlers.py`.
4. Add HTTP-level tests under `tests/` using `ContractClient`.
5. Run `make test` and do not weaken the contract to make a failing implementation pass.

## Repository boundary

```text
harness/                 reusable
  validate_openapi.py    syntax/spec validation
  reset_db.py            disposable SQLite bootstrap
  contract.py            generic request/response contract judge + test-client wrapper

openapi.yaml             Restaurant contract (replaceable)
schema.sql               Restaurant schema (replaceable)
seed.sql                 Restaurant seed (replaceable)
src/                     Restaurant implementation (replaceable)
tests/                   Restaurant acceptance/business tests (replaceable)
```

No ORM, external DB, auth platform, payments, inventory, microservices, Redis, Kafka, MCP server, or product frontend is included.
