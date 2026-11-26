PYTHON ?= python
# .env is plain KEY=value lines, so make can read it and pass it to the scripts.
-include .env
export
export PYTHONPATH := .

.PHONY: setup select fetch attacks budget bench bench-mock report resume test lint

setup:
	$(PYTHON) -m pip install -e ".[dev]"

select:
	$(PYTHON) scripts/select_real.py

fetch:
	$(PYTHON) scripts/fetch_real.py

attacks:
	$(PYTHON) scripts/make_attacked.py

budget:
	$(PYTHON) scripts/budget.py

# Resumable: rerun daily until it reports every cell finished.
bench:
	$(PYTHON) -m triage.run

bench-mock:
	$(PYTHON) -m triage.run --model mock
	$(PYTHON) -m triage.report --mock

report:
	$(PYTHON) -m triage.report

resume:
	$(PYTHON) scripts/resume_bullets.py

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
