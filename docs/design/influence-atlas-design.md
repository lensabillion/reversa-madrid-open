# Influence Atlas Architecture and Delivery Design

3 October 2026. Proposed design requested by the project owner; implementation is planned unless
explicitly marked delivered. Tracked by `rev-f090`. The [consolidated plan](../plan.md)
orders this design's delivery sequence as acceptance gates and settles where it differs
from the uploaded [technical plan](../brief/PLAN.md).

Build an evidence-backed public atlas of who shapes EU law, across procedures since
2019. A reader must be able to follow an actor's request through an amendment to a final
article, compare that request with dated public statements, and inspect the sources.
The system must also answer an unfamiliar law query without code changes. Forecasts
concern ongoing negotiations and must use only information available at their cutoff.

## Requirements and Source of Authority

The controlling source is [The Influence Atlas Challenge Brief](../brief/influence-atlas-challenge-brief.pdf),
12 pages. The [earlier brief](../brief/madrid-open-reversa-challenges.pdf) remains historical
context. The newer brief specifies no supplied dataset, no supplied labels, and no
hidden-pair CSV submission (p. 10). Its hand-in is an explorable graph, a short public
report answering five questions, and a rerunnable open-source repository (p. 6).
Do not interpret the heading “Nothing prepared” as an explicit prohibition on prior code:
the listed rules give no such detailed restriction; organizer clarification remains open.

| Requirement | Brief | Design and acceptance evidence |
| --- | --- | --- |
| Actor → ask → amendment → final article since 2019 | pp. 4, 6 | Typed graph, dated sources, version alignment and visible coverage |
| WHO influences most; WHAT topics | p. 5 | Outcome rankings by topic/year, denominators and uncertainty |
| TOWARDS what; HOW through channels | pp. 5–7 | Structured positions, dated public voice, meeting/consultation/coalition evidence |
| NEXT: rising actors and future wins | pp. 5–6 | Temporal forecasts, cutoff, reasons, held-out evaluation |
| Three random links checked live: 25 points | p. 9 | Every displayed inferred link opens exact source passages and limitations |
| Any EU law named live: 20 points | p. 9 | Generic identifier/title lookup and incremental law pipeline; timed unfamiliar-law rehearsal |
| Checkable insight: 25 points | p. 9 | Five report answers computed from reproducible queries |
| Publishable report and rerunnable repo: 15 points | pp. 9–10 | Source appendix, reproduction instructions, open licence and clean-checkout rehearsal |
| Europe coverage and reasoned forecast: 15 points | p. 9 | Since-2019 inventory, per-stage coverage and explicitly partial results |
| Five-minute demos at 19:30 | p. 11 | Atlas inspection, unfamiliar-law lookup, report, forecast and coverage |

The five questions are report requirements, not five separate scoring categories.
The schedule is local Madrid time on 3 October 2026. Global registers are an extension
(p. 7); prioritize the EU path before adding jurisdictions.

## Latest Merged PR Assessment

GitHub metadata checked on 3 October: [PR #19](https://github.com/lensabillion/reversa-madrid-open/pull/19)
merged at 10:41:56 Madrid time, commit `b4b5444`; #20 merged at 10:35:08.
All nine checks on #19 report SUCCESS. Inspected the merged submission schema, service,
CLI, tests and retained rehearsal documentation. These checks are existing CI evidence,
not a new full-suite run or proof of influence accuracy.

#19 supplies validated JSON Lines input, existing lexical comparison, bounded scores,
`pairs.csv`, evidence JSON Lines, and a web-independent CLI. Reuse its validation and
comparison path internally. It does not discover a law, retrieve candidate sources,
resolve actors, connect final outcomes, create an atlas, or forecast adoption.
Its default 60 pairs and 19:00 deadline describe the old brief. Keep the command available
as a diagnostic tool; it is no longer the primary competition deliverable.

The two output renames are individually atomic, not a transaction. A reused output folder
can contain new evidence beside an old CSV if the last rename fails. The new atlas design
therefore publishes a fresh run directory and marks completion only after validating all
artifacts. The CLI currently reports that the CSV was not replaced on an output error;
do not treat file presence alone as a successful run.

#20 supplies a practice harness. Its presence does not establish trustworthy negative
labels or transfer from historical GDPR copies to post-2019 EU laws. Preserve the label
semantics audit and grouped evaluation work.

## Architecture

Use the eight-part architecture in the repository's concurrently revised
[influence-architecture skill](../../.agents/skills/influence-architecture/SKILL.md).
This technical design supplies contracts and verification detail for those parts; it
must not introduce a second pipeline. The companion Atlas explainer is being prepared under `rev-sz6q`; this document
adds technical contracts without replacing that work.

Retain Python 3.14, uv, FastAPI and Next.js. Thin HTTP routes and command-line adapters
call the same services. Keep one implementation for each job. No scoring runs inside
frontend components, and no prototype code from `attic/` enters the pipeline.

```mermaid
flowchart LR
  query[Law query or since-2019 inventory] --> collect[1 Collect public records]
  collect --> actors[2 Resolve actors]
  actors --> retrieve[3 Find candidates]
  retrieve --> verify[4 Verify links]
  verify --> outcomes[5 Trace outcomes]
  outcomes --> graph[6 Atlas graph]
  graph --> analyse[7 Analyse ranks positions and forecasts]
  graph --> publish[8 Publish explorer and report]
  analyse --> publish
  collect --> outcomes
  practice[Practice and temporal evaluation] -.-> verify
  practice -.-> analyse
```

| Part | Existing home to extend | Responsibility and output |
| --- | --- | --- |
| 1 Collect | `services/documents.py`, `repositories/`, `schemas/` | Resolve procedures, cache public records, preserve versions and extract amendment changes |
| 2 Resolve actors | Repository joins and new typed identity records | Register IDs and evidenced aliases; unresolved identities remain separate |
| 3 Find candidates | Comparison services and passage-finder work | Extract bounded ask passages and retrieve high-recall candidate pairs |
| 4 Verify links | `services/scoring.py`, `services/comparison.py`, `services/submission.py` | Signals and precise evidence-backed assessments, separate from labels |
| 5 Trace outcomes | New service under `services/` | Align legal versions and record full/partial/unknown observed outcomes |
| 6 Atlas graph | Extend `services/demo.py`; typed graph records | Actor/ask/amendment/article paths and dated context |
| 7 Analyse | New services consuming graph snapshots | Coverage-aware rankings, public voice/channels and time-cutoff forecasts |
| 8 Publish | Existing frontend workspace and thin routers | Explorer, generic law command, report and reproducible release |
| Practice | `influence/practice/` | Audited labels, retrieval checks, grouped/temporal splits, robustness and runtime |

The brief's MAP layer uses 1–6; RANK and EXPLAIN use 7; FORECAST also uses 7;
all are exposed by 8. Parts 3 and 5 also consume the source records produced by 1.
Implementation may add concrete files to these homes; names below describe proposed
contracts, not endpoints or commands that already exist. Public graph and ranking views
use supported/published links only; lower-confidence candidates remain accessible in a
clearly separated audit view and do not count as established influence.

## Records and Evidence Contracts

Start with typed JSON Lines snapshots and a small local SQLite index for identifiers,
search and joins if the law inventory requires it. SQLite is a proposed standard-library
storage choice; benchmark before adding graph or vector databases. Preserve raw public
files under ignored `data/`. Publish derived records and a source manifest only where
redistribution terms permit; otherwise publish retrieval instructions and excerpts.

| Record | Required information |
| --- | --- |
| SourceDocument | Stable ID, public URL, source kind, publication and retrieval times, content hash, language, extraction status, reuse terms |
| Procedure | Procedure ID, title, CELEX aliases, topic, status, dated versions and known coverage gaps |
| Actor | Stable internal ID, register IDs, names and aliases, actor kind; unresolved identities remain separate |
| Ask | Actor, procedure, cited passage, requested change, target provision, direction, scope, date, extraction method and uncertainty |
| Amendment | Procedure, committee, number, authors, original/proposed wording, date, evidence spans |
| ArticleVersion | Procedure, version stage/date, provision identifier, text and source spans |
| PublicPosition | Actor, dated statement and source, topic, direction and scope; distinguish self-statement from news attribution. Not implemented: no part collected or read one, so the record was removed from `schemas/atlas.py` on 6 October 2026; it returns with the part that produces it |
| EvidenceLink | Typed endpoints/relation, supporting spans, signals, method revision, time eligibility, assessment status and limitations |
| Outcome | Ask, law stage, full/partial/not observed/unknown result, aligned final spans, completeness and method |
| Forecast | Ask, as-of time, horizon/event definition, score type, reasons, feature snapshot and model revision |
| RunManifest | Inputs, revisions, configuration, stage counts/errors, timings, output inventory and completion status |

A source span stores document ID, page when available, half-open Unicode code-point
start/end offsets and the quoted text. Retain the original text and translated text with
an alignment reference. Frontend slicing uses `Array.from`, as in the existing contract.
Unknown dates cannot silently satisfy “published before amendment.” Unknown outcomes and
unresolved identity must remain unknown, not zero or a confident merge.

Graph relations include actor REQUESTED ask, ask SUPPORTED_BY source, ask ECHOED_BY
amendment, amendment TABLED_BY person, amendment EDITS provision, provision ALIGNED_TO
later version, and ask REALIZED_IN article. Meetings and coalition membership are dated
context edges. A meeting does not prove transmission of an ask. Historical volunteer
labels remain practice/comparison records and never masquerade as our inferred edges.

## Law Discovery and Data Pipeline

Accept a procedure ID, CELEX identifier, or law title. Resolve ambiguous titles by showing
candidate procedures. Build connectors by source family, not by individual law: legislative
metadata and amendments, Have Your Say submissions, EUR-Lex/Publications Office versions,
Transparency Register identities, and published meeting records. The source list on p. 7
is a discovery menu, not evidence that every API is currently accessible.

For each law, resolve identifiers; retrieve/cache documents; extract dated asks; identify
amendments and authors; retrieve candidate passages; assess links; align adopted text;
build graph and summary. Record each stage's coverage and failures. Results can appear
incrementally, but incomplete sources cannot support an “all actors” or “no influence”
claim. Cached evidence remains labelled with its retrieval date.

Maintain a since-2019 procedure inventory separately from completed analysis. The scope
boundary is proposed as procedures with legislative activity since 1 January 2019,
including older files still active then; display that definition and confirm it with the
organizers. Counts distinguish discovered, downloaded, extracted, matched and outcome-
aligned procedures. GDPR historical evidence can validate plumbing but does not count
as post-2019 coverage without qualifying legislative activity.

Bound network retries and stage budgets, persist successful source work, and allow rerun
from the manifest. Missing required text prevents the corresponding link, while unavailable
meetings or public statements leave explicit gaps. A law with no usable evidence returns
an explained partial result rather than fabricated actors. No arbitrary promise that
all EU law will be analyzed in minutes: measure uncached and cached paths separately.

## Matching and Observed Wins

Extract an ask as a requested policy change, not an entire document. Preserve actor,
regulated subject, obligation/permission/prohibition, quantities, exceptions, beneficiaries
and time constraints. One submission may hold several asks; keep them distinct.
Compare amendment changes against the original law where known. Missing originals remain
`null`; do not fabricate a change from a whole passage.

Candidate retrieval first narrows by procedure, provision, time and topical text, then
keeps several bounded passages with surrounding context. Measure evidence retrieval
recall before scoring. Shared quotations of the original law must not dominate. Signals
include rare changed phrases, edit direction, alignment, and evaluated paraphrase support;
negation, changed numbers and shall/may reversals require explicit counter-evidence.
External model/provider selection remains open; this design authorizes no API spend or
new provider integration.

Until independently evaluated calibration exists, show a support score and method, not
an influence probability. Separate candidate, supported, contradicted and insufficient-
evidence statuses. Freeze display thresholds on development data. Show alternatives when
several actors share the same ask: text reuse can support an association, not unique
causal authorship. A source published after an amendment cannot be presented as its origin.

Align provisions across draft, Parliament position and final law using text and structure,
not article numbers alone. Record insertions/deletions and partial fulfillment. “Heard”
means echoed by an amendment; “adopted by Parliament” and “realized in final law” are
separate outcomes. Final agreement may originate elsewhere or have multiple contributors.

For each actor/topic/year, publish distinct asks, assessed asks, full/partial wins, unknown
outcomes and source coverage. The default full-win rate is full wins divided by asks
with assessed outcomes; show partial wins separately and the unknown count beside it.
Deduplicate repeated filings and amendments that repeat the same ask; do not multiply a
win by author count. Coalition asks retain joint attribution. Avoid ranking budget as
influence. Rankings with tiny denominators display counts and uncertainty, and are
explicitly rankings within observed coverage.

## Public Voice and Channels

Compare a dated public position with the specific ask on the same topic, scope and time.
Display aligned, conflicting, mixed or insufficient evidence, with both quotations.
Publicly disclosed submissions cannot reveal undisclosed private intent. The brief's
public/private comparison is operationalized as public messaging versus published
lobbying requests; do not claim access to private communications.

Consultations, meetings, tabling MEPs, coalitions and timing can describe an observed
sequence. Report “associated with observed wins” when analyzing channels, not “caused
wins.” Missing meetings are missing records. Executive statements do not automatically
represent a corporation's position; source attribution must state the speaker.

## Forecasts and Rising Actors
i
Forecast whether a dated, specific ask will appear fully or partially in a defined future
law stage. Freeze an as-of cutoff before that stage. Separate forecasts from retrospective
text-survival outcomes. A live file without a known event date carries an explicit horizon
and an unresolved outcome until the event occurs.

Begin with a documented baseline using pre-cutoff amendment support, stage, topic and
historical outcomes where available. Actor growth compares coverage-adjusted activity and
success over disclosed windows; raw mention growth can reflect changing data collection.
A forecast card includes reasons, missing features and uncertainty. Without adequate
labels and temporal validation, publish a reasoned scenario/ranking rather than a
calibrated numerical probability. Do not use final texts or later meetings as forecast
features. Evaluate against a simple prevalence baseline on rolling time splits, reporting
AUC, Brier score/calibration when probabilities exist, sample counts and per-topic limits.

## Atlas Interface and Public Report

The law page shows source coverage, actor/ask/amendment/article paths, filters for topic,
year and relation status, and an evidence drawer. Each inferred edge opens side-by-side
passages, date eligibility, scorer method and counter-evidence. The actor page separates
requests, observed outcomes, public voice, channels and forecasts. Search must support
unfamiliar laws without a source-code change.

The short report contains five sections: WHO, WHAT, TOWARDS, HOW and NEXT. Each answer
includes a reproducible graph query, scope and denominator, at least one source-backed
case and a limitation. Add methodology, coverage, source appendix and reproduction
instructions. Do not fill it with invented findings before running the atlas. It should
be readable without the dashboard, with links that permit independent inspection.

Public release requires an open code licence (confirm project-owner licence choice),
source reuse review, commands from a clean checkout, frozen tool/model revisions and an
output manifest. Public accessibility is not blanket permission to redistribute whole
third-party documents. Only public sources are used; personal data stays limited to
attributed public legislative roles needed for the analysis.

## Delivery Sequence and Verification

| Order | Work package | Completion test |
| --- | --- | --- |
| 1 | Generic law resolver, source manifest, one current-law vertical slice | An unfamiliar identifier loads without code changes; partial failures are visible |
| 2 | Ask extraction, passage retrieval, scored evidence links | Every displayed link opens valid quotations; hard decoys and paraphrases are evaluated |
| 3 | Final-version alignment and ask outcomes | Renumbered/partial/unknown cases are tested; rates deduplicate requests |
| 4 | Atlas explorer and five-question report export | Three random displayed links can be independently checked; report claims reproduce |
| 5 | Since-2019 inventory, incremental expansion and channels/public voice | Coverage denominators match manifests; inaccessible sources remain visible |
| 6 | Forecast baseline and temporal evaluation | No post-cutoff features; reasons and evaluation limits accompany predictions |
| 7 | Clean-checkout and live-demo rehearsal | Five-minute demo plus uncached named-law run with time/hardware/stage timings |

These packages are a delivery order, not a claim that one historical law satisfies the
Europe-wide ambition. Grow corpus coverage alongside the working vertical slice and
publish its gaps. Use incremental outputs so broad data acquisition cannot erase the
verified slice before 19:30.

Reuse existing unit/contract/property/gate checks. Add tests for identifier ambiguity,
source/date provenance, exact spans, polarity, multilingual evidence, passage retention,
identity collisions, duplicate asks, legal renumbering, partial outcomes, unknown
coverage and temporal leakage. Evaluate new scores on audited public labels and
actor/procedure-separated folds; synthetic cases diagnose failures but do not prove
field accuracy. Unlike the old no-human-label hidden-test rule, the new brief has no
supplied test set: public-source evaluation annotations may be kept separately with
provenance, never substituted for automated model output.

Random-link rehearsal samples from all displayed supported links with a retained seed,
not a curated selection. Record precision and errors as well as three jury-style checks.
Measure candidate retrieval and source extraction separately from pair ranking. Set a
proposed unfamiliar-law target of five minutes, then report measured cached/uncached
results and source availability; the brief says “minutes” without a fixed bound.

## Decisions and Open Questions

Authorized by this request: use the second brief as the current challenge contract and
prepare the revised design. The eight-part architecture is a proposal pending owner
review/merge; graph/report/reproducibility are requirements from the PDF. Reusing existing
services is the implementation recommendation.
Proposed implementation choices: local snapshots/index, activity-since-2019 scope,
full-win-rate denominator and five-minute query budget. They need measurement or explicit
owner/organizer resolution before being treated as proven or required.

Open: exact scope of “any law,” treatment of ongoing/pre-2019 files, startup/cache policy
for the live check, permissibility of advance preparation, licence choice, semantic judge,
coverage achievable today, and sufficient temporal adoption labels. No clarification is
needed to begin the generic law/evidence path. Old CSV-schema and recall-threshold
questions cease to block that path.

Rejected: a graph made from historical verification flags (does not show our analysis),
a spending leaderboard (does not measure wins), similarity-only links (fails the random
check), one-law hard coding (fails the live lookup), fabricated probabilities, a database
stack before measured need, and training a large model before a working evidence path.

## Verification of This Design Change

Read all 12 pages of the second PDF by page-preserving pypdf extraction. Read PR #19's
merged source, description and all nine successful GitHub check receipts. Ran the existing
submission and CLI tests on the checkout:

```text
pytest tests/test_submission.py tests/test_cli.py --no-cov -q
33 passed in 1.31s
```

`git diff --check` passed. A new full `make check` and visual PDF rendering were not run;
no implementation, model improvement, coverage expansion or forecast result is claimed.
The documentation gate validates research catalogs, not prose correctness. Concurrent
project-wide replanning under `rev-sz6q` remains responsible for the explainer, architecture
skill and wider bead reconciliation; its in-progress files were preserved.
