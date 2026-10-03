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
	check-backend-quality check-backend-tests audit-backend fix-backend dev-backend submit setup collect atlas coordinated lineage channels directions audit-sample audit-score forecast batch \
	frontend-env check-frontend check-frontend-quality check-frontend-tests \
	check-frontend-build audit-frontend fix-frontend dev-frontend fetch-lobbyplag fetch-qwen-embedding fetch-qwen-reranker evaluate-dense

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

# The any-law command: collect, then parts 3 to 7, into data/laws/<procedure>/atlas.json.
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

# Atlas part 3, from Parltrack alone: the amendments and Members collect already read.
coordinated:  ## List near-identical amendments tabled across political groups: make coordinated LAW='2021/0106(COD)' [ARGS=--no-attachments]
	$(if $(LAW),,$(error LAW is required: make coordinated LAW='2021/0106(COD)'))
	$(BACKEND) influence coordinated "$(LAW)" $(ARGS)

# Lineage, outcome-first: the final act's new wording traced to amendments and documents.
lineage:  ## Trace one law's adopted wording to its amendments and documents: make lineage LAW='2021/0106(COD)' [ARGS=--no-attachments]
	$(if $(LAW),,$(error LAW is required: make lineage LAW='2021/0106(COD)'))
	$(BACKEND) influence lineage "$(LAW)" $(ARGS)

channels:  ## Count the channels one law was lobbied through: make channels LAW='2021/0106(COD)' [ARGS=--no-attachments]
	$(if $(LAW),,$(error LAW is required: make channels LAW='2021/0106(COD)'))
	$(BACKEND) influence channels "$(LAW)" $(ARGS)
# Atlas part 7, TOWARDS: rule-based directions of the amendments and, through the atlas
# view's published links, of each actor's asks.
directions:  ## Count which way amendments and actors' asks move a law: make directions LAW='2021/0106(COD)' [ARGS=--no-attachments]
	$(if $(LAW),,$(error LAW is required: make directions LAW='2021/0106(COD)'))
	$(BACKEND) influence directions "$(LAW)" $(ARGS)
# Atlas part 7, NEXT: reads every written atlas view; forecasts the named open laws' asks.
# More laws go in ARGS, quoted one by one: ARGS="'2020/0361(COD)'".
forecast:  ## Forecast the open asks of laws with an atlas view: make forecast LAW='2021/0106(COD)' [ARGS=...]
	$(if $(LAW),,$(error LAW is required: make forecast LAW='2021/0106(COD)'))
	$(BACKEND) influence forecast "$(LAW)" $(ARGS)

# Gate 7, the blind audit: labels live under data/audit/ only, never in a law's view.
audit-sample:  ## Draw two blind reader sheets from a view: make audit-sample LAW='2021/0106(COD)' SEED=<n> [SIZE=40] [ARGS='--status unconfirmed']
	$(if $(LAW),,$(error LAW is required: make audit-sample LAW='2021/0106(COD)' SEED=<n>))
	$(if $(SEED),,$(error SEED is required: make audit-sample LAW='2021/0106(COD)' SEED=<n>))
	$(BACKEND) influence audit sample "$(LAW)" --seed $(SEED) $(if $(SIZE),--size $(SIZE)) $(ARGS)

audit-score:  ## Score two filled sheets against the key: make audit-score DIR=data/audit/<slug>/<sample-id>
	$(if $(DIR),,$(error DIR is required: make audit-score DIR=data/audit/<slug>/<sample-id>))
	$(BACKEND) influence audit score "$(abspath $(DIR))"

# Plan gate 9: many laws at once, resumable, with a coverage banner in data/laws/batch.json.
batch:  ## Collect many laws and run the per-law steps: make batch ARGS="--laws 'AI Act,DSA'" or ARGS='--since 2019 --with-amendments'
	$(if $(ARGS),,$(error ARGS is required: make batch ARGS='--since 2019 --with-amendments'))
	$(BACKEND) influence batch $(ARGS)

# First brief only: the 19:00 pairs command. $(BACKEND) runs inside backend/, so paths are
# made absolute here. EXPECTED_PAIRS is passed only when set, so the command's own default
# (60) stays the one copy.
submit:  ## Score PAIRS (JSON Lines) into OUT/pairs.csv: make submit PAIRS=<file> OUT=<dir>
	$(if $(PAIRS),,$(error PAIRS is required: make submit PAIRS=<file> OUT=<dir>))
	$(if $(OUT),,$(error OUT is required: make submit PAIRS=<file> OUT=<dir>))
	$(BACKEND) influence submit --pairs "$(abspath $(PAIRS))" --out "$(abspath $(OUT))" $(if $(EXPECTED_PAIRS),--expected-pairs $(EXPECTED_PAIRS))

# The snapshot is pinned to a commit and verified against recorded SHA-256 digests.
fetch-lobbyplag:  ## Download and verify LobbyPlag's data into data/lobbyplag/ (needs network).
	$(BACKEND) python ../scripts/fetch_lobbyplag.py

# The Qwen model files (about 1.8 GB) are pinned to a Hugging Face commit and verified by SHA-256.
fetch-qwen-embedding:  ## Download and verify Qwen3-Embedding-0.6B (ONNX, 8-bit) into data/models/ (needs network).
	$(BACKEND) python ../scripts/fetch_qwen_embedding.py

fetch-qwen-reranker:  ## Download and verify Qwen3-Reranker-0.6B (ONNX) into data/models/ (needs network).
	$(BACKEND) python ../scripts/fetch_qwen_reranker.py

# The optional `models` dependency group holds the model runtime; nothing else installs it.
evaluate-dense:  ## Measure the Qwen meaning signals on LobbyPlag (needs the models; see make fetch-qwen-*).
	uv run --directory backend --locked --group models python -m influence.practice.dense \
		--data "$(abspath data/lobbyplag)" --model "$(abspath data/models/qwen3-embedding-0.6b)" \
		--reranker "$(abspath data/models/qwen3-reranker-0.6b)" \
		--cache "$(abspath data/models/cache.sqlite3)" --out evaluation/dense-meaning.json

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
