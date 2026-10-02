# Influence Graph Backend

This service provides the public GDPR evidence needed for the first Challenge 03 demo:
browse amendments, inspect proposed changes alongside lobby submissions, and show the
organizations and authors connected by historically verified links. An amendment is a
proposed edit to a law; a submission records changes an organization requested.

The [organizers' brief](../docs/brief/madrid-open-reversa-challenges.pdf), pages 12–15,
also requires semantic influence scoring and adoption forecasting. This backend is the
starting evidence demo and an executable lexical baseline. It does not yet deliver the
two competition CSVs, a trained influence probability, or an adoption forecast.
See the [primer](../docs/explainer/influence-graph-primer.md) for the broader design.
See [implementation status](../docs/implementation-status.md) for verified capabilities,
remaining competition work and handoff instructions.

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

## HTTP Contract

| Method and path | Result |
| --- | --- |
| `GET /health` | Existing status and installed package version |
| `GET /api/v1/demo` | Snapshot counts and coverage caveat |
| `GET /api/v1/amendments` | Stable, paginated summaries |
| `GET /api/v1/amendments/{id}` | Old/new amendment text and up to 20 candidate sources |
| `GET /api/v1/amendments/{id}/graph` | Organization, amendment and author nodes with typed edges |
| `GET /api/v1/organizations` | Recorded proposal, verified-link and distinct amendment counts |
| `POST /api/v1/score` | Deterministic changed-text similarity and source-offset evidence |
| `POST /api/v1/compare` | Explicit edit or whole-passage comparison when originals may be unknown |
| `POST /api/v1/documents/extract` | Page-preserving extraction from PDF or UTF-8 text |

List parameters are `q` (committee, amendment number or author; at most 200 characters),
`offset` (nonnegative), `limit` (1–100, default 20), and `verified_only` (default false).
Multiple search words must all match. Detail sources sort verified first, then by stable
candidate identifier; `total_sources` exposes truncation. They are historical candidates,
not newly retrieved recommendations. Graph edges use only historically verified source
links; author edges record authorship. Counts are observed coverage, not organization
win rates or proof of causation.

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
timings and runtime details. On an Apple M5 (10 CPU cores), loading took 0.030 seconds,
all 4,867 details and graphs took 0.866 seconds, and 60 repeated HTTP requests for one
sample pair took 0.057 seconds. There were 1,933 computed scores, 24 non-English sources
with explicit unavailable scores, and no sources omitted by the detail limit. These are
single-run smoke measurements, not an accuracy evaluation or the complete competition
pipeline's timing. The five input files matched the pinned upstream snapshot byte for byte.

The implementation and validation evidence are tracked in **rev-ic1h**. The remaining
competition evaluation and adoption work is tracked in **rev-p2rd**, **rev-zzur** and
**rev-104q**. This README describes the delivered backend; tbd remains the work tracker.
