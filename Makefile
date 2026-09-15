PYTHON ?= python3

.PHONY: generate db-reset test experiment smoke postgres-bootstrap postgres-start postgres-stop postgres-status clean-results

generate:
	$(PYTHON) data/generate_smoke_data.py

db-reset: generate
	./scripts/load_smoke_data.sh

test:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) tests/verify_database.py

experiment:
	$(PYTHON) experiments/run_smoke.py
	$(PYTHON) tests/verify_results.py

smoke: db-reset test experiment

postgres-bootstrap:
	./scripts/bootstrap_postgres_macos.sh

postgres-start:
	./scripts/postgres_local.sh start

postgres-stop:
	./scripts/postgres_local.sh stop

postgres-status:
	./scripts/postgres_local.sh status

clean-results:
	./scripts/clean_results.sh
