# influence Backend

The backend collects public records for one EU law, traces wording from the final act
through amendments to consultation documents, and writes `lineage.json`. The website
reads that view. Shared wording and model judgments are associations, not proof of causal
influence; the recorded limitations and unknown states remain part of the response.

## Supported Commands and API

From the repository root, using Python 3.14 and uv:

```sh
make setup                         # once per machine; downloads public source inputs
make collect LAW='AI Act'           # collect only; optional before lineage
make lineage LAW='AI Act'           # collect, trace, write lineage.json
make dev-backend                    # http://127.0.0.1:8000
```

`make lineage LAW='AI Act' ARGS='--jev --jev-max-usd 1'` additionally judges reworded
origins using the existing optional Jev integration. It requires `TYPESAFE_API_KEY` and
respects the supplied cost cap. No model call is made by the website or API.

To serve committed snapshots instead of downloading data:

```sh
INFLUENCE_DATA_ROOT="$PWD/mock-data" make dev-backend
```

Use an absolute environment path: the Make target runs inside `backend/`. The default
root is the repository's `data/`. The API exposes only `GET /health`,
`GET /api/v1/lineage`, and `GET /api/v1/lineage/{slug}`, plus FastAPI's documentation.
The home page redirects to `/lineage`. `make up` serves the same API and frontend in
containers; `INFLUENCE_DATA=./mock-data make up` mounts the committed snapshots.

`INFLUENCE_LOG_LEVEL` accepts `debug`, `info` (default), `warning`, `error` or `critical`.
`INFLUENCE_VIEW_MAX_AGE` sets view cache lifetime in seconds. Invalid values fail startup.
HTTP requests only read saved views; collection and analysis run through the CLI.

The Atlas producer and its offline forecast, report, audit, directions, channels,
coordinated-amendment and batch commands are retired. So are the standalone extraction
probe and model/practice experiment runners. Historical documents and recorded evaluation
JSON remain, with the former instructions in [the archived backend guide](README-history-2026-10-07.md).
Existing ignored data is not deleted, but `atlas.json` is no longer read or produced.

## Runtime Boundaries

Collection, source identities, passages and manifests retain their persisted `atlas-1`
record format; the shared schema filename is not an Atlas output dependency. Lineage
keeps lexical adoption/origins and optional BM25/Jev origins. Its result remains
`lineage-1`, compatible with the committed snapshots. Browser aggregation and graph
layout remain in the existing frontend; no forecast or ask-level win-rate model is used.

## Setup Command

`influence setup` (`make setup`) fetches, once per machine, the global files every
`influence collect` run reads, to the paths `CollectInputs.under` names under the data
root (`INFLUENCE_DATA_ROOT`, default the repository's `data/`, or `--data-root`). Bead
`rev-6c1o`. It needs network access to `parltrack.org` and `ec.europa.eu`.

```sh
make setup                                       # everything; the index crawl is the long part
make setup ARGS='--only parltrack,register'      # the five required files only (about 310 MB)
make setup ARGS='--only hys'                     # the index alone, for example in another terminal
make setup ARGS=--refresh                        # fetch every chosen file again and replace it
```

| Group | Writes | From |
| --- | --- | --- |
| `parltrack` | `raw/parltrack/{ep_dossiers,ep_amendments,ep_plenary_amendments,ep_meps}.json.zst` | `https://parltrack.org/dumps/<name>.json.zst` |
| `register` | `raw/registry/register.xml` | `https://ec.europa.eu/transparencyregister/public/files/ODP/download/XML/latest` |
| `hys` | `catalog/hys-index.jsonl` | `hys.crawl_index`: about 42 list pages and one request per initiative (about 4,128) |

Groups run in that order, so the required files are in place before the long crawl.

**Downloads.** `CachedFetcher.download` streams each bulk file in 1 MiB chunks through
the fetching layer's identity and rate limit, into a temporary file that is renamed over
the target only when the whole body arrived with a 2xx status. A short body (fewer bytes
than the declared Content-Length; Python's `http.client` returns such a body without
raising), a refusal or a dead host leaves the previous file, or none. Bulk files bypass the
HTTP cache: the file on disk is the stored copy. Beside each downloaded file,
`<name>.source.json` holds its `SourceDocument`: URL, retrieval time (when the request
left), SHA-256 and media type. For a dump it is the same record collect writes into a
law's `documents.jsonl`.

**The index.** The crawl reads and fills the HTTP cache under `data/cache/`. The index is
written only when every initiative answered: a partial one would make collect report "no
feedback" for a skipped law. The first failure stops the crawl; a rerun replays the cached
answers and asks only for the rest. `--refresh` asks every page again, so an interrupted
refresh starts over.

**Reruns.** A file already present is not fetched and is reported `kept`; it is still
hashed for the table. A file put there by hand has no `.source.json`, and setup does not
invent one. Collect keys its `amendments` stage by the SHA-256 of the committee, plenary
and MEP dumps and its `asks` stage by those of the export and the index, so after a
refresh the next `make collect` redoes those stages. The dossiers dump is in no stage key:
a refreshed one rebuilds the procedure catalog, but a law already collected keeps its
saved stages, and with them the title and status the older dump gave, until
`make collect ARGS=--refresh`.

**Output.** One row per file, after the run: path, bytes, the first 12 hex digits of its
SHA-256, and `fetched`, `built` or `kept`. Index progress goes to stderr every 250
initiatives.

**Stops.** Exit 1 at the first file that cannot be fetched or built, after listing the
files finished before it; exit 2 for an unknown `--only` group.

**Measured** (cloud container, 4-core Xeon 2.8 GHz, Python 3.14.7, a 120,000,000-byte file
served from `127.0.0.1`): the streamed download, written and flushed to disk, took 0.97 to
1.03 s with a peak RSS rise of 4 MB; the whole-body read the cache path uses took 0.25 s,
writing nothing, and its peak RSS rose 167 MB. **Not verified:** a run against
the real hosts, which this container's network policy blocks, so real download times, the
real Content-Length and redirect behaviour, and the crawl's duration (about 35 minutes
uncached, as reported in `docs/agents/agent-1-handoff.md`) are not measured here.
## Collect Command

`influence collect <law>` turns what a person types into one law's public record, as the
shared `atlas-1` records of `schemas/atlas.py`. It is plan gate 1 (`docs/plan.md`, §8)
and bead `rev-pjk2`. It joins the connectors that already exist and adds no source of its
own:

| Step | Connector | Writes |
| --- | --- | --- |
| Resolve the query | `services/law_query.py` (shapes, the common-name table `LAW_ALIASES`, title ranking) over a catalog built from Parltrack's dossiers; CELLAR only for a CELEX or COM number the catalog lacks | the procedure, or the choices when a name or title is unclear |
| `texts` | `repositories/cellar.py`: identifiers by SPARQL, acts as XHTML, split into provisions; a proposal's annex streams are fetched too and split at their "ANNEX I" headings, one provision per annex as in the final act (a lost or unsplit annex stream leaves the proposal layer `partial`, naming the stream) | `documents`, `document_texts`, `articles` |
| `amendments` | `repositories/parltrack.py`: committee and plenary dumps, then the MEPs who tabled them | `documents` (the dumps), `amendments`, `actors` |
| `asks` | `repositories/hys.py` joined by COM reference only; `services/passages.py`; `services/actors.py` over `repositories/register.py` | `documents`, `document_texts`, `passages`, `actors` |
| `law` | merges the stages | `laws.jsonl` (one `LawRecord` with ten typed coverage rows), `actors.jsonl` |

From the repository root:

```sh
make collect LAW='2021/0106(COD)'
make collect LAW='AI Act' ARGS=--no-attachments   # faster; the asks layer is then partial
# equivalent: uv run --directory backend --locked influence collect "2021/0106(COD)"
```

**Resolving the query.** What was typed is tried in this order, and the first that fits
decides:

1. A procedure number (`2021/0106(COD)`), CELEX number (`32024R1689`) or COM reference
   (`COM(2021) 206`), recognised by shape.
2. A common name from `LAW_ALIASES` in `services/law_query.py`: 84 names for 28
   procedures, in English, German, French and Spanish, such as `AI Act`, `KI-Verordnung`,
   `Ley de IA`, `DSA`, `GDPR`, `RGPD` and `CSDDD`. Case, accents, punctuation, spacing and
   a surrounding "the" do not matter (`the ai act`, `AI-Act` and `Reglement sur l'IA` all
   match), but the whole name must match: `AI` or `AI Acts` do not. The name stands for
   its procedure number, and that procedure must be in the dossiers dump; if it is not,
   the command stops and says so, because every listed law predates the dump. Two names
   spelt alike for different procedures, or a name that is exactly another procedure's
   title, print the choices instead of picking one.
3. A title search over the catalog's titles. A close race prints the top three choices.

The command prints the procedure it resolved and that dossier's title before any stage
runs, for example
`Resolved 'AI Act' to 2021/0106(COD), titled 'Artificial Intelligence Act' in the
Parltrack dossiers dump`, so a wrong law can be stopped before it takes minutes.

PR #49 started the table with seven names (`ai act`, `aia`, `dsa`, `dma`, `csddd`,
`cs3d`, `ehds`), each resolved against the real Parltrack catalog. The others were checked
against a public EUR-Lex or Legislative Observatory page or this repository's research
tables, not against the real catalog or CELLAR. To add a name, check its procedure number
on EUR-Lex or the Legislative Observatory first: a wrong entry analyses the wrong law under
a name the reader trusts. A test checks that every procedure number has the form
`2021/0106(COD)`, that no two names are spelt alike, and that every name reaches its own
procedure. The table is in code rather than in `data/catalog/aliases.jsonl`, as
`docs/plan.md` §5 proposed, because `data/` is never committed. Resolving a name against a
synthetic catalog the size of the real one (23,886 titles) took 146 ms when every title
was ASCII and 328 ms when most held an accent, against 169 to 182 ms for a title search
(`measured`, median of seven runs, 4-core Xeon at 2.8 GHz, 3 October 2026).

**Inputs.** Five files must exist under the data root (`INFLUENCE_DATA_ROOT`, default the
repository's `data/`, or `--data-root`); the command stops before any request, naming the
missing ones:

| File | Source |
| --- | --- |
| `raw/parltrack/ep_dossiers.json.zst`, `ep_amendments.json.zst`, `ep_plenary_amendments.json.zst`, `ep_meps.json.zst` | `https://parltrack.org/dumps/<name>` (ODbL) |
| `raw/registry/register.xml` | `https://ec.europa.eu/transparencyregister/public/files/ODP/download/XML/latest` |

`catalog/hys-index.jsonl` (the Have Your Say initiatives by COM reference) is optional.
Without it the consultation is found by a title search, and the coverage row says so.
`make setup` downloads the five files and builds the index; see
[Setup Command](#setup-command).

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
unreadable, the query names no procedure or several (the choices are printed), a common
name's procedure is not in the dossiers dump, or the law has neither amendments nor
consultation submissions. An optional source that fails
(CELLAR, a publication the API does not serve, an attachment) becomes a labelled
coverage gap instead.

**Not verified.** The command is tested offline on a small world written in the real
formats (`tests/test_collect.py`, 50 tests). It has not been run on real sources from the
cloud session that wrote it, whose network policy blocks the EU hosts, so its real-data
counts and timings are not measured yet.
## Lineage View API (the Explorer's View)

`influence lineage <law>` writes `lineage.json` (see "Lineage Command (Outcome First)" below)
and prints the explorer URL, `http://localhost:3000/lineage?law=<slug>`. The API reads the
written views back (`services/lineage_views.py`, `routers/lineage.py`), from the same data
root as the command (`INFLUENCE_DATA_ROOT`, default the repository's `data/`):

| Endpoint | Answer |
| --- | --- |
| `GET /api/v1/lineage` | `{"laws": [{slug, procedure_id, title, run_id, status, adopted_phrases, amendments_adopting, documents_with_origin}]}` for every law with a `lineage.json`; a count is null when the view could not compute it |
| `GET /api/v1/lineage/{slug}` | The `LineageView`. 404 when the law has no view; 422 for a malformed slug; 500 when the file on disk is invalid |

Both routes are cacheable, because a view changes only when `make lineage` rewrites its
file, and it does so atomically (a rename), so the file's size and modification time
identify its content without reading it (`routers/view_cache.py`):

- `Cache-Control: public, max-age=<seconds>`: a browser or shared cache may reuse its copy
  for that long. The seconds come from `INFLUENCE_VIEW_MAX_AGE` (default 3600), read when
  the API starts; anything but a whole number of seconds, 0 or more, stops the API with an
  error naming the variable. `0` makes every reuse a revalidation.
- `ETag`: a weak tag (`W/"…"`) hashed from the installed package version and each view
  file's slug, size and modification time in nanoseconds. For the list it covers every
  view, so it changes when any view is added, rewritten or removed. It is weak because the
  same file is served gzip-compressed or plain depending on the client, and RFC 9110
  requires a strong tag to differ between those representations; `If-None-Match` compares
  weakly, so revalidation works the same.
- `Last-Modified`: the view file's modification time; for the list, the newest view's
  (absent when there is none).
- A request whose `If-None-Match` matches the current tag (RFC 9110, section 13.1.2: weak
  comparison, a comma-separated list or repeated fields, or `*`) answers `304 Not Modified`
  with the same three headers and no body, after one `stat` per view file and no read.
  `If-Modified-Since` is not evaluated, so a client sending only that gets a 200.
- 404 and 500 answers keep their messages and carry `Cache-Control: no-store`.

`tests/fixtures/lineage/view.json` is the offline test world's view, regenerated with
`uv run --directory backend --locked python tests/test_lineage_views.py`; the frontend
tests read it, so its TypeScript types are checked against real backend JSON
(`tests/test_lineage_views.py` fails when the committed file drifts).
## Lineage Command (Outcome First)

`influence lineage <law>` (`make lineage LAW='2021/0106(COD)'`) collects the law, then
starts from the final act: every stretch of it that is not in the Commission's proposal and
that an amendment's new text holds (a run of at least 8 words with an inserted word and 3
of the law's rare words) is an adopted phrase, keyed by its place in the final act, so one
stretch is never counted twice. It then searches the law's consultation documents (Have
Your Say feedback and attachments, never the law's own texts) for the adopted wording and
for wording amendments inserted that was not adopted. The output is
`data/laws/<procedure>/lineage.json` (`schemas/lineage.py`, `LineageView`), written
atomically, with `status`, `reason`, `counts`, `adopted_phrases`, `tabled_phrases`,
`adoptions`, `origins`, `credits` and `limitations`.

**Reworded origins with Jev** (`--jev`, `make lineage LAW='AI Act' ARGS='--jev'`). Verbatim
search misses requests made in other words. With `--jev` (key in `TYPESAFE_API_KEY`;
`--jev-max-usd`, default 1), `services/lineage_jev.py` takes each adopting amendment, lets
part 3's BM25 shortlist the 5 consultation passages that share its rare changed words, and
asks Jev PR #63's frozen four-question prompt for each pair (`services/jev_judge.py`).
A pair whose four answers all clear 0.67 becomes an origin of kind `semantic`, quoting the
whole passage, with `similarity` set to the weakest supporting answer and dated like a
verbatim origin. Answers are cached under `data/cache/jev/` by request hash. BM25 bounds
what Jev sees (recall@5 0.663 on LobbyPlag's verified pairs), and adoption itself stays
word for word.

Counting follows `docs/plan.md` section 7. Every holder of a phrase is credited with the
whole phrase and a shared one is flagged joint (no fractional credit); each credit carries
the amendments adopted and the amendments tabled, so Members are ranked by rate per
amendment tabled ("N of M"). An amendment with no resolved author is credited to the group
or name it gives, and to the committee text only when no carrier of the phrase names an
author. An author whose group is unknown credits no group (`phrases_without_group`). A
document counts as an origin only when it is dated before every carrying amendment
(`eligibility` "ask_first") and is not a citation. Without the proposal or the final act the
view is `status: "unknown"` with its reason, and every count that could not be computed is
null, never zero. The website retains its existing sample display; no independent
precision audit is established by this cleanup.

## Verification

Run `make check-backend` for locked dependencies, Ruff, strict basedpyright, unit/API
tests, gate probes, and 100% line and branch coverage. Run `make check` for the entire
repository, including frontend build and vulnerability audits. Tests use small synthetic
snapshots and do not require the downloaded public corpus or network access. tbd remains
the work tracker; this README describes the delivered backend.
