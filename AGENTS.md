# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.
Humans follow the same rules. `CLAUDE.md` imports this file, so there is one copy.

<!-- BEGIN TBD INTEGRATION format=f08 surface=agents-md -->
## tbd

This repository uses **tbd** for git-native issue tracking (beads), spec-driven
planning, and on-demand engineering guidelines.
As the agent, you operate tbd on the user’s behalf: translate their requests into tbd
actions rather than telling them to run commands.

- Run `tbd prime` to load current project state and the full tbd workflow.
- Run `tbd skill` for the complete reusable tbd skill instructions.
- Run `tbd shortcut --list` and `tbd guidelines --list` for on-demand resources.
- Track all work as beads: `tbd create`, `tbd ready`, `tbd start`, `tbd close`, and
  `tbd sync`.
- Before editing a bead, pull and re-read it, run `tbd start <id>`, then run `tbd sync`
  so other replicas can see the claim.

<!-- END TBD INTEGRATION -->

## What This Project Is

Our entry for Reversa's Challenge 03, **The Influence Atlas**, at the Madrid Open on
Saturday 3 October 2026. It maps who shapes EU law since 2019: whose asks reached
amendments and the final law, who wins, how, and what they will win next. We hand in a
graph the jury explores live, a short public report, and this repository, open source and
rerunnable by anyone.
The organizers replaced the first Challenge 03 brief (Influence Graph: score 60 supplied
pairs into CSVs) at kickoff on 3 October; work done under it is kept where it still serves.
Read [the Atlas explainer](docs/explainer/influence-atlas-primer.md) and the
[organizers' brief](docs/brief/influence-atlas-challenge-brief.pdf) before changing
behavior.

## Where the Project's State Lives

Chat history, a session's context and an agent's local memory files are not sources of
truth: other agents, other tools and teammates cannot see them, and they are lost when a
session ends or is compacted. The repository is the source of truth.

- **Start every session** by reading
  [docs/implementation-status.md](docs/implementation-status.md) (what is built, verified,
  decided and next) and running `tbd ready`.
- **Before a session ends**, record anything the next session needs: state changes and
  verified facts in `docs/implementation-status.md`, decisions with their reasons in its
  Decisions section, and open work as tbd beads. Work that exists only in a chat is lost.

## The Four Project Rules

These come from the project owner and override any default habit.

1. **Every PR explains itself from first principles.** The description assumes the
   reader knows nothing about the domain, the tools, or the code. It explains what
   problem the change solves, the concepts needed to understand it, what each changed
   file does and why, which alternatives were rejected and why, and how it was verified.
   Use [the PR template](.github/pull_request_template.md).
2. **Code is efficient, optimized, evaluated, and tested from several angles.** See
   [Code Quality](#code-quality) and [Testing and Evaluation](#testing-and-evaluation).
3. **tbd is the source of truth for work.** Follow the tbd skill and guidelines, and keep
   beads current: create, start, update with PR links, close with evidence, sync.
4. **Ruff checks and formats Python; Biome checks and formats TypeScript.** No other
   linter or formatter is added for those languages.

## Repository Layout

| Path | Contents |
| --- | --- |
| `backend/` | Python 3.14 service and pipeline (uv project) |
| `frontend/` | Next.js web app (npm project) |
| `scripts/` | Repository checks used by `make` targets and CI |
| `docs/implementation-status.md` | Current state, decisions and next work; read first |
| `docs/plan.md` | The consolidated execution plan: tools, thresholds and acceptance gates in order |
| `docs/design/` | The technical design: record contracts and completion tests per part |
| `docs/brief/` | The organizers' briefs: the current Influence Atlas brief and the superseded first brief |
| `docs/research/` | Research documents and softschema catalogs |
| `docs/explainer/` | The team explainer, in Markdown so GitHub renders it |
| `data/` | Downloaded public data; never committed |
| `attic/` | Local scratch and superseded prototypes; never committed |

## Commands

`make check` is the one gate: it verifies everything and changes nothing.
CI runs the same targets, so a local pass predicts a CI pass.
Each area adds its targets to the root `Makefile` and to this table when it lands.

| Command | What it does |
| --- | --- |
| `make check` | Every gate below except the dev servers; changes nothing |
| `make check-scripts` | Ruff format and lint check of `scripts/` |
| `make check-docs` | Validates every research catalog against its schema |
| `make check-backend` | Locked install, Ruff format and lint, basedpyright strict, tests with gate probes and 100% branch coverage |
| `make audit-backend` | Looks up every package in `backend/uv.lock` in the OSV vulnerability database (needs network) |
| `make check-frontend` | Clean `npm ci`, Biome, Next.js route types and `tsc`, Vitest with gate probes, production build |
| `make audit-frontend` | `npm audit` of `frontend/package-lock.json`; moderate severity or higher fails (needs network) |
| `make fix-scripts`, `make fix-backend` | Apply Ruff's safe fixes, then formatting |
| `make fix-frontend` | Applies Biome formatting and fixes, including unsafe ones such as adding braces |
| `make fetch-lobbyplag` | Downloads LobbyPlag's practice data, pinned to a commit and verified by SHA-256, into `data/lobbyplag/` (needs network) |
| `make fetch-qwen-embedding`, `make fetch-qwen-reranker` | Downloads the Qwen3 embedding and reranker models (ONNX, about 1.8 GB), pinned to a Hugging Face commit and verified by SHA-256, into `data/models/` (needs network) |
| `make evaluate-dense` | Measures the Qwen meaning signals on LobbyPlag into `backend/evaluation/dense-meaning.json`; needs the optional `models` dependency group (`uv sync --group models`) and the two fetches above |
| `make dev-backend` | Serves the API at http://127.0.0.1:8000 (`GET /health`), restarting on changes in `backend/src/` |
| `make dev-frontend` | Serves the web app at http://localhost:3000, reloading on changes |
| `make setup` | Atlas part 1, once per machine (needs network): streams the four Parltrack dumps and the Transparency Register export into `data/raw/`, each published atomically with a `<name>.source.json` provenance record, then builds `data/catalog/hys-index.jsonl` (about 35 minutes uncached, resumable). Present files are kept; `ARGS='--only parltrack,register'` picks groups, `ARGS=--refresh` fetches again. See the backend README, "Setup Command" |
| `make collect LAW='<query>'` | Atlas part 1: resolves a procedure number, CELEX, COM reference, common name (`'AI Act'`, `'DSA'`) or title and writes that law's texts, amendments, submissions, passages and actors, with typed coverage and a run manifest, under `data/laws/<procedure>/`. `ARGS=--no-attachments` skips attachments; `ARGS=--refresh` redoes every stage. See the backend README, "Collect Command" |
| `make atlas LAW='<query>'` | Resolves a procedure number, CELEX, COM reference, common name or title, collects the law, then runs parts 3 to 7 (asks, candidates, link verdicts, outcomes, graph, outcome counts) and writes `data/laws/<procedure>/atlas.json`, which `GET /api/v1/atlas/{slug}` serves to the explorer at `/atlas`. See the backend README, "Atlas Command and View API" |
| `make coordinated LAW='<query>'` | Atlas part 3, from Parltrack alone: collects the law, then lists the amendments whose inserted wording is near-identical and that Members of different political groups tabled, and writes `data/laws/<procedure>/coordinated.json`. `ARGS=--no-attachments` skips attachments, which this command does not read. See the backend README, "Coordinated Amendments Command" |
| `make forecast LAW='<query>'` | Atlas part 7, NEXT, with no network: reads every written `atlas.json`, validates on rolling time splits over the completed laws' decided asks, and forecasts the named open laws' asks into `data/laws/forecast.json`. A probability only when validation beats prevalence, else a reasoned scenario with no score; the rapporteur-draft fallback is reported as not computable (no draft reports are collected). More laws in `ARGS`. See the backend README, "Forecast Command" |
| `make lineage LAW='<query>'` | Lineage, outcome first: collects the law, then traces each stretch of the final act that is new against the proposal to the amendments that carry it and the consultation documents that say it, with whole (never fractional) credit and rates per amendment tabled, into `data/laws/<procedure>/lineage.json`; without the proposal or final act the view is "unknown" with its reason. See the backend README, "Lineage Command (Outcome First)" |
| `make channels LAW='<query>'` | Atlas part 7 (HOW), from collected records alone: collects the law, then counts feedback by consultation stage and submitter, timing against the proposal and completion, amendments by stage, committee, group and tabling Member, cross-group co-signing and coordinated clusters, and reports the votes and meetings coverage rows, into `data/laws/<procedure>/channels.json`. See the backend README, "Channels Command (Part 7, HOW)" |
| `make directions LAW='<query>'` | Atlas part 7, TOWARDS: collects the law, then labels each amendment's direction (stricter, weaker, delete, delay, exempt, add, keep, other, unknown) with transparent English cue rules, counts them by stage, political group and Member and, only through the published links of an existing `atlas.json`, by asking actor, and writes `data/laws/<procedure>/directions.json`. See the backend README, "Directions Command" |
| `make submit PAIRS=<file> OUT=<dir>` | From the first brief: scores a JSON Lines pairs file into `OUT/pairs.csv` and `OUT/pairs.evidence.jsonl`. The Atlas brief has no CSV deliverable; the command stays until part 4 (verify links) replaces it |

Ruff is pinned once, in `backend/uv.lock`; `check-scripts` uses the same binary.

## Workflow

1. **Find or create the bead.** `tbd ready` lists available work.
   Every piece of work, including discovered follow-ups, gets a bead.
2. **Claim it.** `tbd sync --pull`, re-read the bead, `tbd start <id>`, `tbd sync`.
3. **Fit it into the architecture** before designing, with the
   [influence-architecture skill](.agents/skills/influence-architecture/SKILL.md): name
   the part of the Atlas architecture (eight parts plus a practice loop) the work belongs
   to, and build on that part's existing code. Code in `attic/` predates the architecture
   and is never a source.
4. **Load the guidelines** that match the change, in one call, before writing code:
   always `general-eng-agent-principles`; then `python-rules python-modern-guidelines`
   for Python, `typescript-rules typescript-lint-format-rules` for TypeScript, and
   `ci-and-gates-rules supply-chain-hardening general-testing-rules` for tooling, gates,
   dependencies, or tests.
5. **Branch per PR**, named `<type>/<short-topic>`, for example `feat/pair-scorer`.
6. **Commit** with Conventional Commits (`tbd guidelines commit-conventions`): `feat`,
   `fix`, `test`, `refactor`, `chore`, `docs`, `plan`, `research`, `ops`, `process`.
7. **Open the PR** with the template, then wait for every CI check to finish green.
   Absent CI is not passing CI.
8. **Record the PR** on the bead (`tbd update <id> --notes`), close the bead when the PR
   merges with the evidence in `--reason`, and `tbd sync`.

When work naturally splits into layers that depend on each other, use a stack of PRs
(`tbd shortcut stacked-prs`): each PR's base is the branch below it, and they merge
bottom to top with merge commits.

## Pull Requests

- **One concern per PR.** If its purpose cannot be stated in one sentence, split it.
- **The description is part of the deliverable.** Fill every template section.
  Define each term the first time it appears.
  Show the commands run and their real output, not a claim that they passed.
- **State what is not verified.** Measured, verified, and assumed are different things;
  say which applies to every claim.
- **Generated files are named as generated** (lockfiles, tbd surfaces), so the reviewer
  knows not to read them line by line.

## Code Quality

- **Measure before optimizing, then keep the measurement.** Any claim that code is fast
  enough cites a benchmark run, its input size, and the hardware.
  The live "any law" check is the real budget: the jury names an EU law at 19:30 and the
  pipeline must show who shaped it within minutes, with no code changes. Time one law end
  to end, from download and from cache, on the demo laptop.
- **State the complexity** of every non-trivial algorithm in its docstring when it is not
  linear, and the input sizes it was designed for.
- **Prefer the standard library and existing dependencies.** Every new dependency needs
  a stated reason in the PR and must pass the supply-chain rules below.
- **No premature abstraction.** Add an interface when the second implementation exists,
  not before.
- **Types everywhere.** Python passes basedpyright in strict mode; TypeScript passes
  `tsc` with the tsconfig floor from `typescript-lint-format-rules`.
- **Errors are explicit.** No bare `except`, no silently swallowed failures, no fallback
  that hides a missing input. Follow `tbd guidelines error-handling-rules`.

## Testing and Evaluation

Each behavior is checked from the angles that can catch its failures:

| Angle | Question it answers | Tools |
| --- | --- | --- |
| Unit | Does each function meet its contract on representative and edge inputs? | pytest, Vitest |
| Property-based | Does an invariant hold on many generated inputs (for example, a score stays within 0–1, matching is symmetric where it should be)? | Hypothesis, fast-check |
| Contract | Do the API, CLI and data outputs keep their exact shape? | pytest with the FastAPI test client; golden files |
| Gate probes | Do the linters still reject a known violation? | committed probe files run by the gates |
| Evaluation | Does a scoring change raise the precision of the links we publish without losing recall? | the practice harness on LobbyPlag's labelled pairs (organization-grouped folds), plus a blind audit of a random sample of our own published links, reported with a confidence interval |
| Performance | Does one law, named live, finish within minutes? | timed runs on fixed laws, from download and from cache |
| End to end | Does one command turn a procedure number into a graph, rankings and report figures? | a rehearsal on laws not used during development |

Rules that apply to every test (`tbd guidelines general-testing-rules`):

- No vacuous tests: a test must be able to fail because of the code under test.
- Deterministic: fixed seeds printed on failure, injected clocks, no sleeps.
- An empty or skipped selection must never look like a pass.
- Model changes are accepted on evaluation evidence, never on intuition.
  Report the metric before and after, on the same folds and seeds.

## Python

- Python 3.14, managed by uv. Never call `pip` or a bare `python`.
- `backend/` uses a `src/` layout and absolute imports only.
- Ruff configuration lives once, in the root `ruff.toml`; `backend/` extends it.
- Annotations are evaluated lazily in Python 3.14 (PEP 649 and PEP 749), so
  `from __future__ import annotations` is not used.
- Follow `tbd guidelines python-rules`: docstrings explain why, not what; no trivial
  wrappers; `pathlib` over string paths; atomic writes for completed output files.

## TypeScript and Next.js

- This Next.js version is newer than most model training data and has breaking changes.
  Read the relevant guide in `frontend/node_modules/next/dist/docs/` before writing
  Next.js code, and heed deprecation notices.
  `frontend/AGENTS.md` holds the same instruction as a block that `next dev` manages; do
  not edit it by hand.
- TypeScript 7 (the native compiler); Next.js type-checks with the project's own `tsc`.
- Style with Tailwind CSS v4 utility classes. `app/globals.css` only imports Tailwind.
- Run npm only inside `frontend/` (the `make` targets do), so `frontend/.npmrc` applies.
- After changing `biome.jsonc` or `tsconfig.json`, or upgrading Biome or TypeScript, run
  `make check-frontend-tests`: the gate probes prove each rule still rejects its violation.
- Biome is the only formatter and linter, at the floor in
  `tbd guidelines typescript-lint-format-rules`, verified in CI with
  `biome ci --error-on-warnings`.
- Follow `tbd guidelines typescript-rules`: no `any`, exhaustive `switch`, explicit
  `| null` over optional parameters where omission would be a bug.

## Supply Chain

[SUPPLY-CHAIN-SECURITY.md](SUPPLY-CHAIN-SECURITY.md) is binding: no package version
younger than 14 days without a recorded, human-approved exception; install scripts off;
lockfiles committed and installed frozen; GitHub Actions pinned to commit SHAs.

## Data and Challenge Rules

- Public data only, so everything we find can be published. Downloads go under `data/`,
  which is never committed; the scripts that fetch them are, so anyone can rerun.
- The code goes in a public repository with an open licence (a rule of the brief).
- The pipeline produces every link, score and ranking; nobody edits them by hand.
  People may audit a random sample of published links to measure precision; audit
  labels are stored apart from model output and never feed back into the shown graph.
- Keep raw model output separate from human labels and corrections.
- Practice labels come from public datasets (LobbyPlag); record their provenance.
