.PHONY: install validate reset run test demo

install:
	python -m pip install -r requirements.txt

validate:
	python -m harness.validate_openapi openapi.yaml --strict

reset:
	python -m harness.reset_db --db instance/restaurant.sqlite3 --schema schema.sql --seed seed.sql

run: validate reset
	python -m src.app

test:
	./run-tests.sh

demo:
	python demo_fresher.py --negative
