# Repository quality gates. `make check` verifies everything and changes nothing.
# CI runs these same targets, so a local pass predicts a CI pass.

# Supply-chain cool-off: uv ignores any package file uploaded in the last 14 days.
# See SUPPLY-CHAIN-SECURITY.md.
export UV_EXCLUDE_NEWER := 14 days

PYTHON := 3.14
# Ruff is pinned once, in backend/uv.lock. --project keeps the working directory at the
# repository root, so paths stay `scripts` and Ruff reads the root ruff.toml for them.
RUFF := uv run --project backend --locked ruff
SOFTSCHEMA_VERSION := 0.8.1
# Runs a command in backend/. --locked fails instead of rewriting uv.lock when it no
# longer matches pyproject.toml.
BACKEND := uv run --directory backend --locked

.PHONY: check check-docs check-scripts fix-scripts backend-env check-backend \
	check-backend-quality check-backend-tests audit-backend fix-backend dev-backend

check: check-scripts check-docs check-backend audit-backend  ## Run every gate.

check-scripts:  ## Ruff format and lint check of repository scripts.
	$(RUFF) format --check scripts
	$(RUFF) check scripts

fix-scripts:  ## Apply Ruff formatting and safe fixes to repository scripts.
	$(RUFF) format scripts
	$(RUFF) check --fix scripts

check-docs:  ## Validate every research catalog against its schema.
	uv run --no-project --python $(PYTHON) --with softschema==$(SOFTSCHEMA_VERSION) \
		python scripts/validate_catalogs.py

backend-env:  ## Install exactly what backend/uv.lock records, removing anything else.
	uv sync --directory backend --locked

check-backend: check-backend-quality check-backend-tests  ## Run every backend gate.

check-backend-quality: backend-env  ## Ruff format and lint, then basedpyright strict.
	$(BACKEND) ruff format --check
	$(BACKEND) ruff check
	$(BACKEND) basedpyright

check-backend-tests: backend-env  ## Tests, gate probes and branch coverage.
	$(BACKEND) pytest --cov

# `uv audit` is a preview command in uv 0.12.8; the flag opts in and silences its warning.
audit-backend:  ## Look up every package in backend/uv.lock in the OSV vulnerability database.
	uv audit --directory backend --locked --preview-features audit-command

fix-backend:  ## Apply Ruff formatting and safe fixes to the backend.
	$(BACKEND) ruff format
	$(BACKEND) ruff check --fix

dev-backend:  ## Serve the API at http://127.0.0.1:8000, restarting when src/ changes.
	$(BACKEND) uvicorn influence.api:app --reload --reload-dir src --port 8000
