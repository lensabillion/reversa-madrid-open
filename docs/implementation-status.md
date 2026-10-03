# Implementation Status and Handoff

Updated October 2, 2026. Update this file when a capability or its verification changes.
Issue ownership and PR state live in tbd; implementation contracts live in the
[backend README](../backend/README.md). The
[organizers' brief](brief/madrid-open-reversa-challenges.pdf), pages 12–15,
defines the competition deliverables. `attic/` is not an implementation source.

## Objective and Deliverables

Influence scoring estimates whether an amendment borrows from a lobby submission.
Adoption forecasting estimates whether a consultation proposal reaches the final law.
These are different targets. Similar wording alone proves neither influence nor adoption.

The required outputs are `pair_id,influence_score` for 60 supplied pairs and
`proposal_id,p_adopted` for 20 proposals, plus an influence-graph demo. The API serves
the demo and exposes reusable services; it does not replace the CSV deliverables.

## Implemented and Evaluated

| Capability | Evidence | Limit |
| --- | --- | --- |
| Public-data API and lexical baseline | Foundation PR [#10](https://github.com/lensabillion/reversa-madrid-open/pull/10) merged; 74 tests, 100% branch coverage | No trained or calibrated predictor |
| LobbyPlag browsing | All 4,867 amendment detail records rehearsed; 1,957 unique candidate links, 172 verified | Historical verification is separate from computed similarity; unverified links are not negative labels |
| PDF/text ingestion | 16-page organizers' PDF yields 10,569 characters; byte, page, text and expansion limits tested | No OCR, column reconstruction, automatic passage selection or hard parser process isolation |
| Supplied-text comparison | Known originals select edit overlap; unknown originals select whole-passage overlap; explicit validation and Unicode evidence offsets | English lexical baseline, 12,000 characters and 800 tokens per supplied text; passage overlap can reward boilerplate |
| Backend ingestion gate | `make check`: 106 backend tests, 100% coverage (475 statements, 104 branches); baseline frontend 19 tests; both audits clean | Tests establish behavior, not predictive accuracy |

The frontend under `rev-oze0` and `rev-8mwe` implements a light analytical workspace,
historical evidence views, pasted text and PDF/TXT/MD page review. Combined
`make check` passes 106 backend and 38 frontend tests, the production build and audits.
Browser verification covers actual PDF upload/page selection/comparison, historical
evidence and a 390-pixel layout; details are in the
[frontend README](../frontend/README.md). Backend extraction belongs to `rev-i2v8`
([PR #11](https://github.com/lensabillion/reversa-madrid-open/pull/11), all nine CI checks
passed). Do not infer merge status from files present in a worktree.

## Architecture Assessment

The implemented dependency direction is HTTP routers → typed contracts and services →
repositories or extraction/scoring functions. This permits a batch command to call the
same business logic without HTTP. Keep raw documents, extracted passages, model outputs,
and human labels distinct. Do not turn missing original wording into a fabricated edit.

Pretrained rerankers are candidates for semantic features; relevance scores are not
influence probabilities. Training from scratch is unnecessary for a starting point.
Fine-tuning or fitting a small combiner is justified only with trustworthy labels and
held-out gains. A vector database is unnecessary for 60 supplied pairs; revisit retrieval
storage only when measured corpus search requires it.

The main risk is prioritizing interface breadth over measured prediction quality and
complete exports. Current unit coverage cannot establish competition readiness.
The recorded 60-request timing repeats one pair; it is not a diverse full-pipeline
rehearsal. See [the retained measurement](../backend/validation/rehearsal-2026-10-02.json).

## Decisions

Record every decision here with its status and where its reasoning lives.
Open decisions are not settled until the project owner agrees.

| Decision | Status | Reasoning |
| --- | --- | --- |
| Compete in Challenge 03, Influence Graph | Decided 2026-10-02 | [Research](research/research-2026-10-02-reversa-challenges.md); the owner chose it over the recommended Challenge 02 |
| Work in this repository, separate from the earlier ChamberLens audio project | Decided 2026-10-02 | The old repository's code does not apply to this challenge |
| Architecture: seven parts plus a practice loop | Decided 2026-10-02 | [Explainer §11](explainer/influence-graph-primer.md#11-proposed-architecture) |
| Backend: Python 3.14, FastAPI, uv; Ruff, strict basedpyright, 100% branch coverage | Decided 2026-10-02 | PR [#3](https://github.com/lensabillion/reversa-madrid-open/pull/3) |
| Frontend: Next.js 16.3.6, Tailwind CSS v4, Biome, Vitest | Decided 2026-10-02 | PR [#5](https://github.com/lensabillion/reversa-madrid-open/pull/5); D2 in the explainer |
| TypeScript 7 rather than 6 | Decided 2026-10-02, by merging #5 and #8 | PR #5: Next.js 16.3.6 type-checks with the project's own `tsc` |
| `next` 16.3.6 inside the 14-day cool-off | Approved 2026-10-02; clears 2026-10-06 | [SUPPLY-CHAIN-SECURITY.md](../SUPPLY-CHAIN-SECURITY.md); follow-up `rev-h455` |
| Project state lives in the repository, not in sessions | Decided 2026-10-02 | AGENTS.md, "Where the Project's State Lives" |
| D3: the earlier prototype in `attic/` | Decided 2026-10-02: not built on; each part is built fresh from the architecture | It was written before the architecture was decided; the [influence-architecture skill](../.agents/skills/influence-architecture/SKILL.md) applies this |
| D1: language-model judge (none, Jev, Claude or a local model) | **Open** | Explainer §12–13; no API keys on the machine |
| D4: team split | **Open** | Explainer §13 |
| D5: organizer questions: input format, recall threshold, use of the final law's text, advance preparation | **Open**; ask before the event | Bead `rev-qvmx` |

## Next Work in Competition Order

`rev-6i5t` establishes a reproducible starting measurement: the lexical scorer ranks the
preferred submission first in 2/10 frozen synthetic triplets; a pinned local Qwen3
reranker does so in 8/10. The remaining deadline and obligation failures, and high
scores on contradictory submissions, prevent promotion to production. These are
diagnostics, not held-out influence accuracy. See the [complete experiment and raw
results](../backend/evaluation/README.md). The production API still uses the lexical
baseline. The experiment is on `feat/pair-evaluation`; its heavyweight runtime is
isolated and its dependency lock is audited by the normal gate.

Practice data needs independently justified negatives, including same-article proposals
that ask for different changes. Unverified links remain unknown. Keep organizations,
duplicate amendments and duplicate source passages from leaking across evaluation
boundaries. Synthetic paraphrases, opposite requests, changed quantities and boilerplate
are diagnostic cases, not proof of real-world precision. Compare original and proposed
wording with the relevant lobby passage and surrounding context; for whole documents,
measure whether passage selection retains the evidence before evaluating the scorer.

Accept a candidate only with improved top-20 precision and no material recall regression
on the frozen held-out set, reporting counts and per-group results. Choose any recall
threshold on development data under the organizer's scoring contract. Verify source
quotations, report failures and truncation, and time a complete 60-pair run on available
hardware; under ten minutes is a proposed target, not a measurement. Fine-tuning and
probability calibration require adequate independent labels. Adoption remains a separate
target with separate labels and AUC evaluation.

1. `rev-p2rd`: establish practice labels with provenance and lobbyist-grouped folds;
   compare lexical and pretrained semantic candidates using top-20 precision and recall.
   Do not use unverified candidates as known negatives or hand-label hidden test pairs.
2. `rev-zzur`: choose and calibrate the scorer only on held-out evidence; preserve raw
   feature scores, model revisions, seeds and failure reasons.
3. `rev-104q`: implement and evaluate the separate adoption target with AUC. Verify
   available training labels before claiming a trained adoption model.
4. `rev-fkut`: implement automatic passage selection, validated batch inputs, resumable
   processing and atomic CSV outputs; rehearse 60 diverse pairs and 20 proposals within
   the one-hour window, recording failures, elapsed time and hardware.
5. `rev-qvmx`: resolve organizer input-schema and scoring ambiguities. Validate actual
   supplied data on arrival; no implementation can promise arbitrary formats in advance.

## Continuing in Another Chat

Run `tbd prime`, `tbd sync --pull`, and read the relevant bead before claiming it.
Read `AGENTS.md`, the brief, this file and the implementation README. Check Git/PR state
before editing; keep one concern per PR and leave beads open until merge. The active
ingestion and frontend foundations are merged in PRs #11 and #12. The three-column
comparison follow-up is `feat/three-column-evidence`, tracked as `rev-q24c`, with behavior
documented in the frontend README; column-role clarification is `rev-foxs`. Backend
semantic evaluation is isolated on `feat/pair-evaluation` under `rev-6i5t`; no semantic
model has yet replaced the production lexical score. The original checkout's `feat/law-loader` belongs to other
ongoing work. Load data and start services using README commands; never depend on a
previous chat's running server, temporary log or browser state.
