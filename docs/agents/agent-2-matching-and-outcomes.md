# Agent 2 Matching Outcomes and Evaluation

Implement the inference path of the Influence Atlas. Follow
[the Atlas architecture](../explainer/influence-atlas-primer.md#6-the-architecture), [record contracts](../design/influence-atlas-design.md)
and repository AGENTS.md. Own architecture parts 3, 4 and 5, the practice loop, and
forecast inference in part 7. This assignment is ready to dispatch, not already running.

## Scope and Ownership

Own ask/passage extraction, candidate retrieval, comparison/scoring changes, publication
assessment, legal-version alignment, outcome records, audits and forecast evaluation.
Extend existing comparison/scoring services. Add concrete retrieval/outcome/forecast
services and their tests; do not build a separate scorer package.

Agent 1 owns shared schemas, CLI/API assembly and lockfiles. Request contract/dependency
changes through Agent 1. Agent 3 consumes your assessments/outcomes and must not infer
scores inside the graph or UI. Use an isolated worktree and branch per PR.

Existing beads: `rev-aapn`, `rev-nuk5`, `rev-sbrp`, `rev-00x6`, `rev-zzur`, `rev-jaig`,
`rev-uhpq`, `rev-sn3u`, `rev-104q`. Check ownership and pull/read/start/sync before claiming.

## Start in Parallel

Begin after Agent 1 freezes schemas and fixtures. Implement against those fixtures while
real collection proceeds. Input is a law bundle with amendments, feedback/passages,
legal versions, dates and provenance. Output is asks, ranked candidates, assessments,
exact spans and stage-specific outcomes. Keep IDs stable across handoffs.

## Implementation Order

1. Extract atomic requests with context and legal direction. Preserve all nonempty edits,
   including single-word replacements/deletions. Unknown original text is null, distinct
   from a known empty original. Keep original Unicode offsets and reversible normalization.
2. Retrieve bounded passages and alternatives using lexical search first. Compare one
   multilingual encoder only when the retrieval benchmark is ready. Deduplicate overlapping
   chunks and bound repetition credit. Measure evidence retention separately from scoring.
3. Assess chronology, same requested change, polarity/quantities and exact quotations.
   Similarity/relevance is a signal, not an influence probability. Unconfirmed and
   contradicted records remain separate from published links. Invalid quotation spans
   block publication. Fixed 0.85 model likelihood is not an established threshold.
4. Select publication rules on development data and audit a separate random sample.
   Keep human labels separate from automatic outputs. Synthetic tests diagnose failures,
   not real-world accuracy. Do not silently promote historical volunteer labels to edges.
5. Align legal versions by text/structure across renumbered provisions. Emit heard,
   Parliament-position and final outcomes separately. Support full/partial/not observed/
   unknown. Missing final act is not a loss; limited retrieval failure is not proof of
   non-survival. Handle deletion asks against surrounding obligations/context.
6. Build a forecast baseline only when sufficient audited outcomes exist. Freeze pre-event
   features and use rolling temporal splits with procedure/duplicate grouping. No final
   law leakage. Publish scenarios if probability calibration cannot be supported.

Model/provider D1 remains open. Evaluate the shortlist in the Atlas design and model research; do not
make external-provider calls or select a mandatory API key without resolution. Request
runtime dependencies from Agent 1 with measured need and version/licence evidence. Run
one heavyweight evaluation at a time within the shared laptop budget.

## Acceptance and Handoff

Provide contract/unit/property tests for short edits, negation, shall/may, quantities,
Unicode spans, repeated text, alternative passages, missing dates, renumbering, partial
outcomes and unknowns. Evaluate retrieval and link assessments on the same retained
splits/seeds when comparing models, reporting counts and errors. Forecast evidence needs
baseline metrics, sample sizes and temporal leakage checks.

Hand Agent 3 typed assessments and outcomes early through frozen fixtures, then real
records with source provenance. Hand Agent 1 callable services with no HTTP dependency,
revision/config metadata and explicit failures. Each handoff gives branch/PR, bead IDs,
commands/results, fixture versus real-data status, known failures and remaining blockers.
