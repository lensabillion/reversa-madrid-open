# Supply-Chain Security

This file is binding for every human and agent that installs or upgrades a dependency in
this repository. It applies `tbd guidelines supply-chain-hardening` to this project.

## Why

Package registries (PyPI, npm) and GitHub Actions are attacked by publishing malicious
versions of real packages. Most are detected and removed within days. Waiting before
adopting a new version, refusing to run install scripts, and installing exactly what a
reviewed lockfile records remove most of that risk at little cost.

## Rules

1. **14-day cool-off.** Never install or upgrade to a version published less than 14
   days ago, unless an exception below is recorded and approved by a human.
   Agents never approve their own exceptions.
2. **No package code runs at install time.** npm runs with `ignore-scripts=true`; uv
   never builds a dependency from source (`no-build = true`), because a build runs the
   package's own code.
3. **Lockfiles are committed and installed frozen**: `uv sync --locked`, `npm ci`.
   A lockfile diff is reviewed like code.
4. **Pin exactly.** Direct dependencies use exact versions; GitHub Actions use full
   commit SHAs with the release tag in a comment, because a tag can be moved to other
   code and a SHA cannot.
5. **No unpinned one-off runners.** `uvx`, `npx` and similar always name an exact
   version.
6. **Audit in CI.** Dependency audits run in the same gate as tests: `make audit-backend`
   checks every package in `backend/uv.lock` against the OSV vulnerability database.
7. **Do not update for its own sake.** Upgrade for a named reason: a fix, a feature we
   use, or a security advisory.

## How Each Tool Enforces the Cool-Off

| Tool | Setting | Where |
| --- | --- | --- |
| uv | `UV_EXCLUDE_NEWER="14 days"` (`exclude-newer` in project config) | root `Makefile`, `backend/pyproject.toml` |
| npm 11.10+ | `min-release-age=14` | `frontend/.npmrc` |
| GitHub Actions | Choose a release at least 14 days old, then pin its SHA | `.github/workflows/` |

## Exceptions

Each exception names the exact version, the reason (with the advisory ID), the
verification done, the human who approved it, and the date after which the version
clears the window and the exception can be removed.

| Package | Version | Published | Reason | Approved by | Clears window |
| --- | --- | --- | --- | --- | --- |
