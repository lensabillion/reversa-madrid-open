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
# Runs npm inside frontend/, so frontend/.npmrc (cool-off, no install scripts) always applies.
NPM := cd frontend && npm

.PHONY: check check-docs check-scripts fix-scripts backend-env check-backend \
	check-backend-quality check-backend-tests audit-backend fix-backend dev-backend submit setup collect atlas \
	frontend-env check-frontend check-frontend-quality check-frontend-tests \
	check-frontend-build audit-frontend fix-frontend dev-frontend fetch-lobbyplag

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
audit-backend:  ## Look up every package in backend/uv.lock in the OSV vulnerability database.
	uv audit --directory backend --locked --preview-features audit-command

fix-backend:  ## Apply Ruff's safe fixes, then formatting, to the backend.
	$(BACKEND) ruff check --fix
	$(BACKEND) ruff format

dev-backend:  ## Serve the API at http://127.0.0.1:8000, restarting when src/ changes.
	$(BACKEND) uvicorn influence.api:app --reload --reload-dir src --port 8000

# The 19:00 command. $(BACKEND) runs inside backend/, so paths are made absolute here.
# EXPECTED_PAIRS is passed only when set, so the command's own default (60) stays the one copy.
atlas:  ## Collect one law and build its explorer view: make atlas LAW='2021/0106(COD)' [ARGS=...]
	$(if $(LAW),,$(error LAW is required: make atlas LAW='2021/0106(COD)'))
	$(BACKEND) influence atlas "$(LAW)" $(ARGS)

# Run once per machine before the first `make collect` (needs network). Present files are
# kept, so a rerun after a failure fetches only what is missing.
setup:  ## Download collect's global inputs and build the Have Your Say index: make setup [ARGS='--only parltrack,register']
	$(BACKEND) influence setup $(ARGS)

collect:  ## Collect one law's public record: make collect LAW='2021/0106(COD)' [ARGS=--no-attachments]
	$(if $(LAW),,$(error LAW is required: make collect LAW='2021/0106(COD)'))
	$(BACKEND) influence collect "$(LAW)" $(ARGS)

submit:  ## Score PAIRS (JSON Lines) into OUT/pairs.csv: make submit PAIRS=<file> OUT=<dir>
	$(if $(PAIRS),,$(error PAIRS is required: make submit PAIRS=<file> OUT=<dir>))
	$(if $(OUT),,$(error OUT is required: make submit PAIRS=<file> OUT=<dir>))
	$(BACKEND) influence submit --pairs "$(abspath $(PAIRS))" --out "$(abspath $(OUT))" $(if $(EXPECTED_PAIRS),--expected-pairs $(EXPECTED_PAIRS))

# The snapshot is pinned to a commit and verified against recorded SHA-256 digests.
fetch-lobbyplag:  ## Download and verify LobbyPlag's data into data/lobbyplag/ (needs network).
	$(BACKEND) python ../scripts/fetch_lobbyplag.py

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
