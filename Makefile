PYTHON := python3
VENV := .venv
VENV_PY := $(VENV)/bin/python

.DEFAULT_GOAL := install

.PHONY: venv install test lint format run clean

venv: $(VENV_PY)

$(VENV_PY):
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip

install: venv
	$(VENV_PY) -m pip install -r requirements-dev.txt

test:
	$(VENV_PY) -m pytest

lint:
	$(VENV_PY) -m ruff check .

format:
	$(VENV_PY) -m ruff format .

run:
ifndef WORK_ID
	$(error WORK_ID is required, e.g. make run WORK_ID=123456)
endif
	$(VENV_PY) -m atscraper --work-id $(WORK_ID)

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
