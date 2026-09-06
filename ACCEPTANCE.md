# Acceptance Matrix

| ID | SOW gate | Proof in this repo |
|---|---|---|
| A1 | OpenAPI valid before execution | `harness/validate_openapi.py`, `tests/test_harness.py::test_a1_openapi_valid` |
| A2 | Clean deterministic DB | `harness/reset_db.py`, `tests/test_harness.py::test_a2_clean_db_is_deterministic` |
| A3 | Contract judge catches bad response | `tests/test_harness.py::test_a3_contract_judge_catches_intentionally_wrong_response` |
| A4 | Menu contract | `tests/test_menu.py` |
| A5 | Customer + duplicate email | `tests/test_customers.py` |
| A6 | Reservation success/capacity/double booking | `tests/test_reservations.py` |
| A7 | Transactional order + server prices | `tests/test_orders.py::test_a7_*` plus defense-in-depth price-field test |
| A8 | Complete joined order read | `tests/test_orders.py::test_a8_get_order_returns_joined_item_details` |
| A9 | State machine | `tests/test_orders.py::test_a9_order_state_machine` |
| A10 | Customer history | `tests/test_orders.py::test_a10_customer_order_history` |
| A11 | Fresh DB repeat | `run-tests.sh` runs the complete suite twice; fixtures create disposable DBs |
| A12 | Harness reusability | `tests/test_harness.py::test_a12_harness_contains_no_restaurant_business_vocabulary` and the `harness/` boundary |
| A13 | Second-Fresher dogfood | `tests/test_dogfood.py`, `demo_fresher.py`, README Swagger walkthrough |

The manual A13 proof is strongest when a person starts from a clean DB, uses only `README.md` + `/docs`, and does not inspect `src/` first.
