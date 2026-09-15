PYTHON ?= python3
M2_VENV := .venv-milestone2
M2_PYTHON := $(M2_VENV)/bin/python
M2_READY := $(M2_VENV)/.ready

.PHONY: generate db-reset test experiment smoke postgres-bootstrap postgres-start postgres-stop postgres-status clean-results m2-setup m2-acquire m2-test m2-preflight m2-qualification

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

$(M2_READY): requirements-milestone2.txt
	$(PYTHON) -m venv $(M2_VENV)
	$(M2_VENV)/bin/python -m pip install --upgrade pip
	$(M2_VENV)/bin/python -m pip install -r requirements-milestone2.txt
	$(M2_VENV)/bin/python -c "import h5py, numpy, pgvector, psycopg, psutil"
	touch $(M2_READY)

m2-setup: $(M2_READY)

m2-acquire: $(M2_READY)
	$(M2_PYTHON) scripts/acquire_sift1m.py

m2-test: $(M2_READY)
	$(M2_PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

m2-preflight: $(M2_READY)
	$(M2_PYTHON) -m experiments.milestone2.runner --config config/milestone2/preflight-10k.json

m2-qualification: $(M2_READY)
	$(M2_PYTHON) -m experiments.milestone2.runner --config config/milestone2/qualification-100k.json
