PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
PIP := $(VENV_PYTHON) -m pip
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000

.PHONY: test setup setup-api setup-integrations setup-dev check-local smoke-api run-backend

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v

# The setup targets install Python packages only. System FFmpeg, FFprobe,
# espeak-ng, and libsndfile are installed through the platform package
# manager; see README.md and `make check-local` for the corresponding checks.
# backend/requirements.txt also carries python-multipart for File/Form/UploadFile.
setup: setup-integrations

setup-api: $(VENV_PYTHON)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

setup-integrations: setup-api
	$(PIP) install -r backend/requirements-integrations.txt

setup-dev: setup-api
	$(PIP) install -r backend/requirements-dev.txt

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

check-local:
	$(PYTHON) tests/check_local_setup.py

smoke-api:
	$(PYTHON) tests/smoke_api.py --base-url http://$(BACKEND_HOST):$(BACKEND_PORT)

run-backend: setup-api
	$(VENV_PYTHON) -m uvicorn app.main:app --app-dir backend --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)
