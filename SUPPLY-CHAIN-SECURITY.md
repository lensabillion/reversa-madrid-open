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
| `next`, `@next/env` and eight `@next/swc-*` binaries | 16.3.6 | 2026-09-22 | 16.3.5 has the critical advisory GHSA-vcvr-r3jv-pc5j; 16.3.6 is the first fixed version (note 1) | Lensa Billion, by merging PRs #5 and #8 on 2026-10-02 | 2026-10-06 |
| `source-map-js` (transitive: postcss, `@tailwindcss/node`, jsdom's css-tree) | 1.2.2 | 2026-09-30 | 1.2.1 has the high advisory GHSA-68fv-2mgg-jv7q (CVE-2026-93749); 1.2.2 is the first fixed version and `make audit-frontend` fails on every branch until it is taken (note 2) | The owner, by merging PR #89 | 2026-10-14 |

Notes:

1. **next 16.3.6.** [GHSA-vcvr-r3jv-pc5j](https://github.com/advisories/GHSA-vcvr-r3jv-pc5j)
   allows remote code execution through `next/og` `ImageResponse` in versions 16.2.0 to
   16.3.5. `next` pins `@next/env` and its eight platform `@next/swc-*` binaries to its own
   version, so all ten packages share the publication date. Verified before installing:
   published by GitHub Actions through npm trusted publishing with SLSA provenance;
   integrity
   `sha512-L+otWM/aQbYTx98aZhgEoMb4bZAXx1YVW4UMA/vuCyCoWG5HJyZUili8QAkqzrcC+5///tsz3s0M+SlyB5bLMw==`;
   no advisory affects 16.3.6. The rest of the tree resolved under the policy first; one
   `npm install next@16.3.6 --min-release-age=0` then changed only these ten packages.
   16.3.7 and 16.3.8 fix no advisory, so they are not taken.

2. **source-map-js 1.2.2.** [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)
   (CVSS 7.5): a crafted indexed source map makes `SourceMapConsumer` spin the event loop,
   a denial of service, in versions 1.0.0 to 1.2.1. In this repository the package runs
   only at build and test time (postcss and Tailwind on our own CSS, jsdom's css-tree in
   Vitest), never on input from outside, so the exposure is to the audit gate rather than
   to users; the exception keeps that gate honest instead of ignoring it for eight days.
   Verified before installing: the GitHub compare `v1.2.1...v1.2.2` of
   `7rulnik/source-map-js` holds four commits (the CVE fix #79, a CSP fix #29, the
   changelog and the version bump) touching `lib/` and `test/` only; the package has no
   install scripts (and `ignore-scripts` is on regardless); the lockfile's integrity
   `sha512-KGj/8Y43x35aZVDtt+J4mK1hoLGHULMYfSkODJNQjNDC3oW1PqPoxMwo0pLUsWM/UEGzON/NxeHywEfNXNP3Vw==`
   equals the registry's; postcss's range `^1.2.1` resolves to it, so `package.json` is
   unchanged and no other package moved. The package carries no npm provenance
   attestation; it is published by the maintainer account `7rulnik`, as every earlier
   version was. The exception was installed with `npm update source-map-js
   --min-release-age=0` and expires when the version clears the window.
