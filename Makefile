# Repository quality gates. `make check` verifies the default gates and changes no source.
# CI runs these same targets, so a local pass predicts a CI pass.

# Supply-chain cool-off: uv ignores any package file uploaded in the last 14 days.
# See SUPPLY-CHAIN-SECURITY.md.
export UV_EXCLUDE_NEWER := 14 days

# Next.js sends anonymous usage data to Vercel unless this is set. Gates make no such calls.
export NEXT_TELEMETRY_DISABLED := 1

PYTHON := 3.14
# Ruff is pinned once, in backend/uv.lock. --project keeps the working directory at the
# repository root, so paths stay `scripts` and Ruff reads the root ruff.toml for them.
RUFF := uv run --project backend --locked ruff
SOFTSCHEMA_VERSION := 0.8.1
# Runs a command in backend/. --locked fails instead of rewriting uv.lock when it no
# longer matches pyproject.toml.
BACKEND := uv run --directory backend --locked
# Runs npm inside frontend/, so frontend/.npmrc (cool-off, no install scripts) always applies.
NPM := cd frontend && npm

.PHONY: check check-docs check-scripts fix-scripts backend-env check-backend \
	check-backend-quality check-backend-tests audit-backend fix-backend dev-backend \
	check-evaluation-runtime audit-evaluation-runtime \
	frontend-env check-frontend check-frontend-quality check-frontend-tests \
	check-frontend-build audit-frontend fix-frontend dev-frontend

# Audits come last: they need network access, and the local gates fail faster.
check: check-scripts check-docs check-backend check-frontend audit-backend audit-frontend  ## Run every gate.

check-scripts:  ## Ruff format and lint check of repository scripts.
	$(RUFF) format --check scripts
	$(RUFF) check scripts

# Lint fixes first, then formatting, so the formatter has the last word on layout.
fix-scripts:  ## Apply Ruff's safe fixes, then formatting, to repository scripts.
	$(RUFF) check --fix scripts
	$(RUFF) format scripts

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
audit-backend: audit-evaluation-runtime  ## Audit production and experiment dependency locks.
	uv audit --directory backend --locked --preview-features audit-command

# The frozen experiment has a separate heavyweight environment; normal CI audits its
# lock without downloading model weights or installing PyTorch.
audit-evaluation-runtime:
	UV_EXCLUDE_NEWER=2026-09-18T00:00:00Z uv audit --directory backend/evaluation/runtime --locked --preview-features audit-command

check-evaluation-runtime: backend-env  ## Optional model runtime quality checks; no inference.
	UV_EXCLUDE_NEWER=2026-09-18T00:00:00Z uv sync --directory backend/evaluation/runtime --locked
	$(RUFF) format --check backend/evaluation/runtime
	$(RUFF) check backend/evaluation/runtime
	$(BACKEND) basedpyright --project evaluation/runtime

fix-backend:  ## Apply Ruff's safe fixes, then formatting, to the backend.
	$(BACKEND) ruff check --fix
	$(BACKEND) ruff format

dev-backend:  ## Serve the API at http://127.0.0.1:8000, restarting when src/ changes.
	$(BACKEND) uvicorn influence.api:app --reload --reload-dir src --port 8000

frontend-env:  ## Install exactly what frontend/package-lock.json records; fail if it is stale.
	$(NPM) ci

check-frontend: check-frontend-quality check-frontend-tests check-frontend-build  ## Run every frontend gate.

check-frontend-quality: frontend-env  ## Biome format, lint and import order, then route types and tsc.
	$(NPM) run check:lint
	$(NPM) run check:types

check-frontend-tests: frontend-env  ## Vitest: component tests and gate probes.
	$(NPM) test

check-frontend-build: frontend-env  ## Production build with next build, which type-checks again.
	$(NPM) run build

audit-frontend:  ## Fail on any advisory of moderate or higher severity in frontend/package-lock.json.
	$(NPM) audit --audit-level=moderate

fix-frontend: frontend-env  ## Apply Biome formatting and fixes, including unsafe ones such as adding braces.
	$(NPM) run fix

dev-frontend: frontend-env  ## Serve the web app at http://localhost:3000, reloading on changes.
	$(NPM) run dev
