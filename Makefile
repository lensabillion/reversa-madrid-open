# Repository quality gates. `make check` verifies everything and changes nothing.
# CI runs these same targets, so a local pass predicts a CI pass.

# Supply-chain cool-off: uv ignores any package file uploaded in the last 14 days.
# See SUPPLY-CHAIN-SECURITY.md.
export UV_EXCLUDE_NEWER := 14 days

PYTHON := 3.14
RUFF := uvx --python $(PYTHON) ruff@0.16.8
SOFTSCHEMA_VERSION := 0.8.1

.PHONY: check check-docs check-scripts fix-scripts

check: check-scripts check-docs  ## Run every gate.

check-scripts:  ## Ruff format and lint check of repository scripts.
	$(RUFF) format --check scripts
	$(RUFF) check scripts

fix-scripts:  ## Apply Ruff formatting and safe fixes to repository scripts.
	$(RUFF) format scripts
	$(RUFF) check --fix scripts

check-docs:  ## Validate every research catalog against its schema.
	uv run --no-project --python $(PYTHON) --with softschema==$(SOFTSCHEMA_VERSION) \
		python scripts/validate_catalogs.py
