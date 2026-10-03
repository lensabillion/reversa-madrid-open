# Influence Graph Backend

This service provides the public GDPR evidence needed for the first Challenge 03 demo:
browse amendments, inspect proposed changes alongside lobby submissions, and show the
organizations and authors connected by historically verified links. An amendment is a
proposed edit to a law; a submission records changes an organization requested.

The [organizers' brief](../docs/brief/madrid-open-reversa-challenges.pdf), pages 12–15,
also requires semantic influence scoring and adoption forecasting. This backend is the
starting evidence demo and an executable lexical baseline. Its `influence submit` command
writes the first competition CSV, `pairs.csv`, from the lexical comparison score; it does
not yet deliver `proposals.csv`, a trained influence probability, or an adoption forecast.
See the [primer](../docs/explainer/influence-graph-primer.md) for the broader design.
See [implementation status](../docs/implementation-status.md) for verified capabilities,
remaining competition work and handoff instructions.
The [frozen semantic experiment](evaluation/README.md) records the lexical baseline's
failure cases and a local reranker comparison, including why it is not ready to replace
production scoring.

## Run With Public Data

Use the repository's Python 3.14 and uv toolchain. From the repository root:

```sh
uv sync --directory backend --locked
make dev-backend
```

The API is at `http://127.0.0.1:8000`, interactive documentation at `/docs`, and the
machine-readable contract at `/openapi.json`. `/health` and `/api/v1/score` work without
downloaded data. Data routes require these five LobbyPlag files in `data/lobbyplag/`:
`amendments.json`, `proposals.json`, `plags.json`, `documents.json`, and `lobbyists.json`.
The directory is ignored by Git.

For a fresh checkout, download the public snapshot pinned to an upstream commit:

```sh
mkdir -p data/lobbyplag
(for name in amendments proposals plags documents lobbyists; do
  curl --fail --location --output "data/lobbyplag/$name.json" \
    "https://raw.githubusercontent.com/lobbyplag/lobbyplag-data/6880188eb528b5eb00cf7efdadfccdd3d5e73795/data/$name.json" || exit 1
done)
```

Confirm `/api/v1/demo` succeeds after downloading. The loader checks schemas, unique
identifiers, and references across all five files; a partial snapshot returns 503.
These files contain extracted text and source metadata, not the original PDF documents.
Source: [LobbyPlag data](https://github.com/lobbyplag/lobbyplag-data/tree/6880188eb528b5eb00cf7efdadfccdd3d5e73795).

Set `INFLUENCE_DATA_DIR` to an absolute directory to use another snapshot or a packaged
installation. The default resolves the repository's `data/lobbyplag` from the editable
source tree. Each application instance loads its snapshot on the first data request and
keeps it in memory. Restart after replacing files. Failed loads remain retryable.

```sh
INFLUENCE_DATA_DIR=/absolute/path/to/lobbyplag make dev-backend
```

The local frontend origins `http://localhost:3000` and `http://127.0.0.1:3000` are allowed
by CORS. This is a local public-data demo without authentication or deployment hardening.

## Collect Command (Atlas Part 1)

`influence collect <law>` turns what a person types into one law's public record, as the
shared `atlas-1` records of `schemas/atlas.py`. It is plan gate 1 (`docs/plan.md`, §8)
and bead `rev-pjk2`. It joins the connectors that already exist and adds no source of its
own:

| Step | Connector | Writes |
| --- | --- | --- |
| Resolve the query | `services/law_query.py` over a catalog built from Parltrack's dossiers; CELLAR only for a CELEX or COM number the catalog lacks | the procedure, or the choices when a title is unclear |
| `texts` | `repositories/cellar.py`: identifiers by SPARQL, acts as XHTML, split into provisions | `documents`, `document_texts`, `articles` |
| `amendments` | `repositories/parltrack.py`: committee and plenary dumps, then the MEPs who tabled them | `documents` (the dumps), `amendments`, `actors` |
| `asks` | `repositories/hys.py` joined by COM reference only; `services/passages.py`; `services/actors.py` over `repositories/register.py` | `documents`, `document_texts`, `passages`, `actors` |
| `law` | merges the stages | `laws.jsonl` (one `LawRecord` with ten typed coverage rows), `actors.jsonl` |

From the repository root:

```sh
make collect LAW='2021/0106(COD)'
make collect LAW='AI Act' ARGS=--no-attachments   # faster; the asks layer is then partial
# equivalent: uv run --directory backend --locked influence collect "2021/0106(COD)"
```

**Inputs.** Five files must exist under the data root (`INFLUENCE_DATA_ROOT`, default the
repository's `data/`, or `--data-root`); the command stops before any request, naming the
missing ones:

| File | Source |
| --- | --- |
| `raw/parltrack/ep_dossiers.json.zst`, `ep_amendments.json.zst`, `ep_plenary_amendments.json.zst`, `ep_meps.json.zst` | `https://parltrack.org/dumps/<name>` (ODbL) |
| `raw/registry/register.xml` | `https://ec.europa.eu/transparencyregister/public/files/ODP/download/XML/latest` |

`catalog/hys-index.jsonl` (the Have Your Say initiatives by COM reference) is optional.
Without it the consultation is found by a title search, and the coverage row says so. No
command builds the index or downloads the dumps yet; that is a follow-up bead.

**Outputs.** Under `data/laws/<procedure slug>/`: `stages/<stage>/<input hash>/` holds each
stage's JSON Lines files and its receipt; `runs/<run id>.json` and `manifest.json` hold the
`RunManifest`, written last, after every output re-verifies against its hash. Downloads
are cached under `data/cache/`.

**Coverage.** `LawRecord.coverage` has one row per layer, in a fixed order: `metadata`,
`proposal`, `parliament_position`, `final_act`, `committee_amendments`,
`plenary_amendments`, `asks`, `actors`, `meetings`, `votes`. Each row is `complete`,
`partial`, `missing` (the source lacks it), `not_applicable` (no final act while a
procedure is ongoing) or `not_collected` (this run did not obtain it), with a reason and a
count that is `null` when nothing was counted. `parliament_position`, `meetings` and
`votes` are `not_collected` until their connectors exist.

**Reruns.** A stage is reused when its inputs are unchanged: the procedure, the hash of
every Python file of the package (`source_revision`), and the hashes of the dumps,
register and index it read. A code edit therefore redoes the stages. `--refresh` redoes
every stage and refetches answers the HTTP cache holds.

**Stops.** Exit 1, with no manifest published, when a required file is missing or
unreadable, the query names no procedure or several (the choices are printed), or the
law has neither amendments nor consultation submissions. An optional source that fails
(CELLAR, a publication the API does not serve, an attachment) becomes a labelled
coverage gap instead.

**Not verified.** The command is tested offline on a small world written in the real
formats (`tests/test_collect.py`, 41 tests). It has not been run on real sources from the
cloud session that wrote it, whose network policy blocks the EU hosts, so its real-data
counts and timings are not measured yet.

## Atlas Command and View API (Parts 3 to 8)

`influence atlas <law>` (`make atlas LAW='2021/0106(COD)'`) runs `influence collect`, then
`services/pipeline.py` over the collected bundle, then writes `atlas.json` beside it. The
pipeline adds no logic of its own; it calls each part's code in order:

| Step | Code | Writes into the view |
| --- | --- | --- |
| Asks | `asks_from_passages`: one ask per consultation passage, `extraction_method="passage-v0"` | asks the shown links reach |
| Candidates | `services/retrieval.py` BM25, top 5 passages per amendment's changed words | (not shown) |
| Verdicts | `services/assessment.py` on every candidate | links that are `published`, `unconfirmed` or `contradicted` |
| Outcomes | `services/outcomes.py` for each ask's strongest published or unconfirmed link | outcomes |
| Graph | `services/atlas_graph.py` from the same records as the bundle | `snapshot` |
| Counts | `services/atlas_analysis.py`, final-act rows in its order | `rankings` |

The view keeps every record the shown links reach and nothing else, so the frontend
adapter (`frontend/lib/atlas.ts`) re-validates exactly what the graph shows.

| Endpoint | Answer |
| --- | --- |
| `GET /api/v1/atlas` | `{"laws": [{slug, procedure_id, title, run_id, published_links}]}` for every law with an `atlas.json` |
| `GET /api/v1/atlas/{slug}` | The `AtlasView` (`schemas/atlas_view.py`, `atlas-view-1`): coverage, `bundle` with the keys of the frontend's `AtlasBundle` (`documentTexts` in camelCase), `snapshot`, `rankings`, `limitations`. 404 when the law has no view; 422 for a malformed slug; 500 when the file on disk is invalid |

The API reads the same data root as the command (`INFLUENCE_DATA_ROOT`, default the
repository's `data/`; `create_app(atlas_data_root=...)` in tests).

**Limits, stated in every view.** Ask extraction is a stand-in: every passage is one
ask, so outcome counts count passages, not distinct requests. Link thresholds are part
4's placeholders and unaudited. Outcomes are traced only for asks with a published or
unconfirmed link. Tested offline (`tests/test_pipeline.py`); not yet run on real data or
timed.

## Submission Command

`influence submit` is the 19:00 command: architecture parts 1–4 in one run, without the
web server. It reads the supplied pairs (part 1), compares each with the `/compare`
service (parts 2–3), and passes that score through as `influence_score` (part 4) until a
trained combiner exists. From the repository root:

```sh
make submit PAIRS=/absolute/or/relative/pairs.jsonl OUT=outputs/2026-10-03
# equivalent: uv run --directory backend --locked influence submit \
#   --pairs /absolute/pairs.jsonl --out /absolute/outputs --expected-pairs 60
```

The input is our own normalized contract, because the organizers' format is not yet known
(decision D5): a UTF-8 [JSON Lines](https://jsonlines.org/) file, one object per line.

```json
{"pair_id": "P01", "amendment": {"old": "Keep data for 30 days.", "new": "Keep data for 90 days."}, "submission": {"old": null, "new": "Data should be kept for 90 days."}}
```

`old: null` means the original wording is unknown, exactly as in `/compare`; both originals
known selects edit comparison, otherwise whole passages are compared. At 19:00 a small
adapter converts whatever arrives into this shape. `pair_id` must be non-empty, without
surrounding whitespace, control characters or line separators, and unique.

The whole file is validated before anything is scored. Every problem is reported at once
on stderr with its line number and `pair_id`: invalid JSON, schema errors, blank lines,
duplicate identifiers, an empty file, a pair count other than `--expected-pairs` (default
60, from the brief), and texts over the scorer's limits of 12,000 characters or 800 tokens.
Texts are never truncated. Any problem exits with status 1 and writes nothing; usage
errors exit with status 2.

`OUT` receives two files. `pairs.csv` has the header `pair_id,influence_score` and one row
per input pair in input order, with each score written as the shortest decimal that parses
back to the identical float (so ranking ties are neither created nor lost), never in
exponent form. `pairs.evidence.jsonl` holds one line per pair: `pair_id`,
`influence_score` and the full comparison result (mode, method, score, evidence spans,
negation conflict, limitations). Before writing, the command checks that the scored IDs
equal the input IDs in order and that every score is a finite number in [0, 1]. Both files
are staged in `OUT`, fsynced and renamed into place, evidence first and `pairs.csv` last:
a failure leaves no partial file and any previous `pairs.csv` unchanged.

Not handled yet: a whole lobby paper over the 800-token limit fails loudly until the
passage finder (plan step 3, `rev-aapn`) selects the relevant passage; `proposals.csv` is
plan step 4 (`rev-e5xh`). Rehearse the command on 60 public LobbyPlag pairs with
`uv run --directory backend --locked python tests/rehearse_submission.py
/absolute/path/to/lobbyplag`; the [recorded run](validation/submission-rehearsal-2026-10-02.json)
took 0.16 seconds per complete command on an Apple M5, including interpreter start-up.

## HTTP Contract

| Method and path | Result |
| --- | --- |
| `GET /health` | Existing status and installed package version |
| `GET /api/v1/demo` | Snapshot counts and coverage caveat |
| `GET /api/v1/amendments` | Stable, paginated summaries |
| `GET /api/v1/amendments/{id}` | Old/new amendment text and up to 20 candidate sources |
| `GET /api/v1/organizations` | Recorded proposal, verified-link and distinct amendment counts |
| `POST /api/v1/score` | Deterministic changed-text similarity and source-offset evidence |
| `POST /api/v1/compare` | Explicit edit or whole-passage comparison when originals may be unknown |
| `POST /api/v1/documents/extract` | Page-preserving extraction from PDF or UTF-8 text |

List parameters are `q` (committee, amendment number or author; at most 200 characters),
`offset` (nonnegative), `limit` (1–100, default 20), and `verified_only` (default false).
Multiple search words must all match. Detail sources sort verified first, then by stable
candidate identifier; `total_sources` exposes truncation. They are historical candidates,
not newly retrieved recommendations. Counts are observed coverage, not organization win
rates or proof of causation.

Unknown entities return 404. Missing/unreadable files and invalid snapshots return 503
with a structured `detail.code`; filesystem paths are not exposed. A candidate outside
the English scorer's language or input limits retains its source evidence and historical
label, with `score: null` and an explicit `score_unavailable_reason`. Invalid requests
return FastAPI's 422 validation response. OpenAPI defines each successful response schema.

Example request, using a deliberately small synthetic edit:

```sh
curl --fail http://127.0.0.1:8000/api/v1/score \
  -H 'Content-Type: application/json' \
  -d '{"amendment":{"old":"Keep data for 30 days.","new":"Keep data for 90 days."},"submission":{"old":"Keep data for 30 days.","new":"Keep data for 90 days."}}'
```

### User-Supplied Text

`/compare` accepts `amendment` and `submission`, each with `old: string | null` and
`new: string`. Null means original wording is unavailable; an empty string means a
known empty original. When both originals are known, the response uses `mode: edits`
and `method: lexical-delta-v1`. Otherwise it compares both full passages with
`mode: passages` and `method: lexical-passage-v1`; a one-sided original is not used.
The response states that limitation and does not invent changed-text spans. Evidence
offsets reference `new` in passage mode. Both modes remain lexical similarity, not
influence or adoption probabilities, and use the existing character/token bounds.

```sh
curl --fail http://127.0.0.1:8000/api/v1/compare \
  -H 'Content-Type: application/json' \
  -d '{"amendment":{"old":null,"new":"Keep data for 90 days."},"submission":{"old":null,"new":"Keep data for 90 days."}}'
```

### PDF and Text Extraction

Send raw file bytes to `/documents/extract` with `Content-Type: application/pdf`,
`text/plain`, or `text/markdown`. It returns `format`, numbered `pages` with extracted
`text`, `warnings`, and `character_count`. Extraction does not guess which columns are
original/proposed wording or select evidence passages. The same service can be called
by a future batch adapter without HTTP. Files are processed in memory and are not saved.

```sh
curl --fail http://127.0.0.1:8000/api/v1/documents/extract \
  -H 'Content-Type: application/pdf' --data-binary @public-submission.pdf
```

Limits: 8 MiB uploaded, 100 PDF pages, 500,000 extracted characters, 2 MiB expanded
content per page and 16 MiB aggregate page streams. Oversized input returns 413,
unsupported media 415, and invalid/encrypted/empty documents 422 with a safe
`detail.code` and message. PDFs with no text return `ocr_required`; mixed blank pages
remain present with warnings. OCR is not performed. Multi-column/table reading order
requires inspection, because PDF extraction cannot guarantee visual order.

`pypdf==6.19.0` is the one added dependency, pinned through the repository's 14-day
package-age policy. Its context-local decompression limits contain common expansion
cases and external image conversion is disabled. These limits are not a hard memory or
CPU sandbox: this is a local public-document demo, not an internet-facing upload service.

## Separation of Responsibilities

`api.py` assembles the application, per-app lazy dataset provider, CORS, and error
translation. `dependencies.py` connects that provider to FastAPI. `routers/` declares
routes and validates HTTP parameters; it contains no matching or data-joining logic.
`schemas/` defines immutable typed request and response objects. `repositories/lobbyplag.py`
parses and validates the local source files, with no network calls or data writes.
`services/demo.py` joins and aggregates those records. `services/scoring.py` is a pure
function that can also be called by a future batch command without an HTTP server.
`cli.py` is that batch command: a thin `argparse` layer over `services/submission.py`,
which calls the same comparison service as `/compare`.

There is one concrete repository and one scoring implementation. No database, vector
store, model-provider abstraction, or background job system is necessary for this corpus.
Historical `verified` values are returned separately and never supplied to the scorer.
Raw file fields that this demo does not use are ignored; required fields and relationships
are validated before a snapshot becomes available. The upstream candidate file contains
repeated identifiers. Rows with the same candidate identifier, amendment, proposal and
verification value are coalesced; conflicts are rejected. `duplicate_candidate_rows`
reports the coalesced count, and candidate/verified counts refer to unique records.

## Scoring and the ML Decision

`lexical-delta-v1` compares the edits, rather than rewarding common unchanged legal text.
It identifies insertions and deletions, then compares same-operation changed words and
adjacent word pairs. Separate edit runs stay separate. The response includes a bounded
`lexical_similarity` score, extracted changes, matching spans and explicit limitations.
Offsets are half-open Python Unicode code-point indices into the original strings:
insertions reference `new`, deletions reference `old`. A JavaScript frontend should slice
`Array.from(text)` for these offsets, since ordinary JavaScript indices count UTF-16 units.

Numbers, punctuation and negation are retained. A conservative English negation guard
rejects some apparent matches with different changed negations, but it is not a legal
entailment model. The baseline cannot establish authorship, reliably detect paraphrases,
or infer adoption. Input sides are bounded at 12,000 characters and 800 lexical tokens;
at least one side of each edit must contain text. These bounds constrain quadratic diff
work and reject oversized input explicitly rather than silently truncating it.

Pretrained ML is appropriate for the challenge's paraphrase requirement. The research
[tool catalog](../docs/research/influence-2026-10/tools.yaml) identifies
[BGE reranker v2 M3](https://huggingface.co/BAAI/bge-reranker-v2-m3) and
[Qwen3 Reranker 0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B).
Rerankers read both texts together and score relevance; Qwen also accepts task instructions.
They do not require a vector database or training from scratch. A relevance score, even
after mapping it into 0–1, is not a calibrated probability that a submission influenced
an amendment.

Evaluate a pinned pretrained model on changed wording with enough surrounding context
to preserve legal meaning. Compare it with this baseline on the same lobbyist-grouped
practice split, including same-article decoys, paraphrases, opposite requests and changed
numbers. Measure top-20 precision, recall, latency and input truncation before selecting
a model. The current corpus has incomplete volunteer verification; unverified candidates
must not automatically become negative training labels. No trained model or external
model call is hidden behind this demo's score. Adoption prediction needs its own target,
time cutoff, labels and evaluation, tracked separately in tbd.

## Extraction Pipeline Foundations

The demo above reads one downloaded snapshot. The competition demo has to answer for a
law the jury names on stage, which means fetching EU public sources during the event.
`influence.extraction` is the layer that does the fetching and the on-disk bookkeeping.
Its design comes from the
[data extraction playbook](../docs/explainer/Influence%20Atlas%20%E2%80%94%20Data%20Extraction%20Playbook.pdf);
the five rules in that document are restated in `src/influence/extraction/__init__.py`
and every module here obeys them.

**What a source is.** A source is one public dataset or site: the EU Transparency
Register, the Commission's published lobby meetings, the European Parliament's open data
API, EUR-Lex, and so on. `catalog.py` lists all thirteen (A to M) with, for each, its
scope (fetched once, per law, or optional enrichment), what it feeds, and its
verification status. Verification status is part of the contract: `confirmed` means the
provider documents it, `third_party` means a community tool reaches it, `unverified`
means nobody has checked, and `build_yourself` means no feed exists.

**No URL in the catalog has yet been confirmed by a live request from this repository.**
That is why there are no parsers in this layer: a parser written against an imagined
response shape is worse than no parser. `probe` records what each base URL actually
returns, and parsers are written from those recordings.

```sh
# List the catalog; nothing is fetched.
uv run --directory backend --locked python -m influence.extraction sources

# Fetch every base URL in a scope and record status, content type and a 200-character
# sniff of each response. Exits non-zero if any source is unreachable.
uv run --directory backend --locked python -m influence.extraction probe --scope global

# Fetch one URL and keep the untouched bytes plus a provenance file under its source.
uv run --directory backend --locked python -m influence.extraction \
  fetch A https://example.europa.eu/register.xml --name register.xml
```

Data goes under the repository's `data/` directory, which Git ignores. Set
`INFLUENCE_DATA_ROOT` or pass `--data-root` to put it elsewhere. The layout, enforced by
`layout.py`, keeps global sources apart from per-law directories so adding a law never
touches another law's files:

```
data/
  cache/                     # every HTTP response, keyed by SHA-256 of method, URL, body
  raw/
    registry/ meetings_ec/ meetings_mep/ ep_opendata/ probe/
    laws/<procedure-slug>/   # 2021/0106(COD) becomes 2021-0106-COD
      manifest.json
  parsed/                    # one file per table below
```

**The cache is not an optimisation.** A second identical request never leaves the
machine, so a parser can be re-run at 17:00 without re-downloading 400 PDFs, and a rate
limit plus a User-Agent carrying a contact address keeps the team from being blocked
mid-event. `fetching.py` is the only module that touches the network: two requests per
second, standard library only, and a non-2xx response raises instead of being cached, so
a source that returns 503 at 10:00 and works at 11:00 is not remembered as broken.

**The manifest is how a law enters the pipeline.** One procedure identifier resolves
into `manifest.json`, which lists the derived CELEX numbers, the lead committee, the
rapporteurs, the consultation identifier, the document URLs, and an `available` block.
Nothing downstream carries a hardcoded identifier, and the `available` block is the
fail-soft switch: a law with no public consultation still produces a graph from
amendments alone, and the coverage report can say what was missing rather than leaving a
silent hole.

**The six parsed tables** are defined in `tables.py` as typed row models: `actors`,
`meetings`, `asks`, `amendments`, `articles` and `links`. Three choices in them matter.
An `asks` row is one text chunk from one submission, not one submission, because a
position paper carries thirty distinct asks and matching a whole PDF is worthless. Every
row carries `source_url`, `fetched_at` and `extraction_method`, because the jury picks
edges at random and asks to see the original. And rows reject undeclared fields, so a
parser cannot quietly invent a column.

Rows are stored as JSON Lines rather than CSV, because legal text contains every
delimiter, and rather than Parquet, because Parquet needs a new dependency (pyarrow)
that the supply-chain policy has not cleared. The row models are the contract, so
changing the container later changes no parser.

**Entity resolution** (`names.py`) is the join nothing else can do. Only the register and
the Commission's meetings carry a registration identifier; MEP meetings and consultation
submissions carry free text, and roughly half of MEP entries do not use the register's
official name, so a join on name alone looks right and is wrong. `ActorIndex.resolve`
tries four layers in order — registration identifier, normalised exact name, acronym,
then fuzzy token-set similarity above 0.90 — and records which layer fired and with what
score. Two outcomes are deliberately not matches: `ambiguous`, when several registered
organisations fit equally (one parent with twelve national entries), and `unresolved`,
below the threshold. A visible unresolved count is more defensible than a silently wrong
join, and the jury can ask about it.

Not in this layer yet: response parsers for any source, the proposal-to-final-act diff,
amendment PDF parsing, candidate link scoring, and the per-law coverage report. They are
the next work, and each needs a probed response shape first.

## Verification

Run `make check-backend` for locked dependencies, Ruff, strict basedpyright, unit/API
tests, gate probes, and 100% line and branch coverage. Run `make check` for the entire
repository, including frontend build and vulnerability audits. Tests use small synthetic
snapshots and do not require the downloaded public corpus or network access.

Rehearse the real snapshot from the repository root:

```sh
uv run --directory backend --locked python tests/rehearse_demo.py /absolute/path/to/lobbyplag
```

The [recorded run](validation/rehearsal-2026-10-02.json) preserves input hashes, counts,
timings and runtime details. On an Apple M5 (10 CPU cores), loading took 0.029 seconds,
all 4,867 details took 0.854 seconds, and 60 repeated HTTP requests for one sample pair
took 0.072 seconds. There were 1,933 computed scores, 24 non-English sources
with explicit unavailable scores, and no sources omitted by the detail limit. These are
single-run smoke measurements, not an accuracy evaluation or the complete competition
pipeline's timing. The five input files matched the pinned upstream snapshot byte for byte.

The implementation and validation evidence are tracked in **rev-ic1h**. The remaining
competition evaluation and adoption work is tracked in **rev-p2rd**, **rev-zzur** and
**rev-104q**. This README describes the delivered backend; tbd remains the work tracker.

## Atlas Graph and Outcome Consumers

The Atlas consumers use the merged `atlas-1` records in `schemas/atlas.py` and run
without HTTP. Collection, identity resolution, link assessment and outcome inference
remain upstream responsibilities.

- `services.atlas_graph.build_graph` projects published actor → request → amendment
  paths and supported request → final article relations into `GraphSnapshot`. Pass
  explicit snapshot/run IDs and a timezone-aware generation time for deterministic
  replay. The service retains coverage and supporting source spans; it rejects invalid
  joins, mismatched quotations, inconsistent chronology and contradictory outcomes.
  Missing final outcomes add no realization edge. Audit candidates never create public
  paths. It does not use historical LobbyPlag labels.
- `services.atlas_analysis.aggregate_outcomes` consumes laws, actors, requests and
  outcomes, including requests with no published link. It reports distinct requests,
  full/partial/not-observed/unknown outcomes and assessed counts for each actor and
  each stage (`heard`, `parliament_position`, `final_act`). The full-win rate is
  `full / assessed`, or `None` when no outcome is assessed. Partial outcomes receive no
  fractional full-win credit. Missing outcomes remain unknown. This measures observed
  fulfillment, not causal influence.

Requests are deduplicated by canonical `ask_id`, supplied by extraction; these services
do not infer semantic equivalence between different IDs. Equal outcome classifications
from repeated amendments count once while preserving their evidence IDs. Conflicting
classifications for the same request and stage fail explicitly. Joint requests count
once for each attributed actor; actor rows overlap, so use sample totals rather than
summing rows. An undated request may have an observed final outcome without supporting
an origin link in the public graph.

Rankings are ordered within each stage by raw full-win rate descending, then assessed
count descending and actor ID. They carry counts and gaps; a small sample such as 1/1 is
not evidence of reliable superiority. Topic filters match supplied subjects exactly;
year means the first four digits of the procedure reference. No smoothing, spend-adjusted
ranking or forecast is computed. A reported request inventory count that differs from
the supplied distinct requests produces an explicit coverage gap, including empty input.

Rehearse and benchmark the committed, invented two-law bundle:

```sh
uv run --directory backend --locked python benchmarks/atlas_consumers.py
```

The fixture has 6 requests, 6 assessments and 9 stage outcomes. It produces 11 graph
nodes and 9 edges, including 2 published origin links and 1 final realization. Final
outcomes total 2 full, 1 partial, 2 not observed and 1 unknown: 2/5 = 0.4 across assessed
requests. Only one of the two full outcomes has a published origin link, illustrating
why fulfillment and attributed influence are separate.

Measured on Apple M5, Python 3.14.7, 3 October 2026: 1,000 cached fixture projections and
aggregations took 0.1062 seconds (0.1062 ms per run). This tiny in-memory benchmark
excludes ingestion, scoring, network and disk loading; it does not establish full-pipeline
runtime or real-world accuracy. The script retains the inputs and measurement procedure.
