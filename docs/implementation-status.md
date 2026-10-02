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
| LobbyPlag browsing and historical graph | All 4,867 amendment detail/graph records rehearsed; 1,957 unique candidate links, 172 verified | Historical verification is separate from computed similarity; unverified links are not negative labels |
| PDF/text ingestion | 16-page organizers' PDF yields 10,569 characters; byte, page, text and expansion limits tested | No OCR, column reconstruction, automatic passage selection or hard parser process isolation |
| Supplied-text comparison | Known originals select edit overlap; unknown originals select whole-passage overlap; explicit validation and Unicode evidence offsets | English lexical baseline, 12,000 characters and 800 tokens per supplied text; passage overlap can reward boilerplate |
| Backend ingestion gate | `make check`: 106 backend tests, 100% coverage (475 statements, 104 branches); baseline frontend 19 tests; both audits clean | Tests establish behavior, not predictive accuracy |

The frontend is being delivered separately under `rev-oze0` and `rev-8mwe`: light
analytical workspace, historical evidence/network views, pasted text and PDF/TXT/MD
page review. Its final validation and PR belong in its README and bead. Extraction
belongs to `rev-i2v8`. Do not infer merge status from files present in a worktree.

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

## Next Work in Competition Order

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
ingestion branch is `feat/document-ingestion`; the separate frontend branch is
`feat/evidence-workspace`. The original checkout's `feat/law-loader` belongs to other
ongoing work. Load data and start services using README commands; never depend on a
previous chat's running server, temporary log or browser state.
