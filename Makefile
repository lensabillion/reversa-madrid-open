# Repository quality gates. `make check` verifies everything and changes nothing.
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
# Every npm command runs inside frontend/, so frontend/.npmrc (cool-off, no install
# scripts) always applies.
FRONTEND := frontend

.PHONY: check check-docs check-scripts fix-scripts backend-env check-backend \
	check-backend-quality check-backend-tests audit-backend fix-backend dev-backend
.PHONY: install-frontend check-frontend lint-frontend typecheck-frontend test-frontend
.PHONY: build-frontend audit-frontend fix-frontend dev-frontend

check: check-scripts check-docs check-backend audit-backend check-frontend  ## Run every gate.

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
audit-backend:  ## Look up every package in backend/uv.lock in the OSV vulnerability database.
	uv audit --directory backend --locked --preview-features audit-command

fix-backend:  ## Apply Ruff's safe fixes, then formatting, to the backend.
	$(BACKEND) ruff check --fix
	$(BACKEND) ruff format

dev-backend:  ## Serve the API at http://127.0.0.1:8000, restarting when src/ changes.
	$(BACKEND) uvicorn influence.api:app --reload --reload-dir src --port 8000

install-frontend:  ## Install exactly what frontend/package-lock.json records; fail if it is stale.
	cd $(FRONTEND) && npm ci

# Ordered cheapest first. Each gate is also a target of its own, for the CI jobs.
check-frontend: lint-frontend typecheck-frontend test-frontend build-frontend audit-frontend  ## Run every frontend gate.

lint-frontend: install-frontend  ## Biome format, lint and import-order check (verify only).
	cd $(FRONTEND) && npm run check:lint

typecheck-frontend: install-frontend  ## Generate Next.js route types, then type-check with tsc.
	cd $(FRONTEND) && npm run check:types

test-frontend: install-frontend  ## Vitest: component tests and gate probes.
	cd $(FRONTEND) && npm test

build-frontend: install-frontend  ## Production build with next build (type-checks again).
	cd $(FRONTEND) && npm run build

audit-frontend:  ## Fail on any known advisory of moderate or higher severity in the lockfile.
	cd $(FRONTEND) && npm audit --audit-level=moderate

fix-frontend: install-frontend  ## Apply Biome formatting and fixes, including unsafe ones.
	cd $(FRONTEND) && npm run fix

dev-frontend: install-frontend  ## Start the Next.js development server.
	cd $(FRONTEND) && npm run dev
