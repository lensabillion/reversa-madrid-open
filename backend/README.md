# Influence Atlas Backend

The Python service and pipeline behind our Influence Atlas entry (Reversa Challenge 03,
[Atlas brief](../docs/brief/influence-atlas-challenge-brief.pdf)). The `influence`
command collects one EU law's public record (proposal, amendments, final act,
consultation feedback and its senders), proposes and verifies links from an
organization's ask to an amendment, traces each ask to the final law, and writes a view
per law under `data/laws/<procedure>/`, which the API serves to the explorer. Further
commands list coordinated amendments, the channels a law was lobbied through and the
direction of each amendment. The [Atlas explainer](../docs/explainer/influence-atlas-primer.md)
explains the design from first principles; the
[implementation status](../docs/implementation-status.md) records what is verified,
decided and next.

Two pieces built for the superseded first brief remain because the Atlas uses them: the
lexical comparison (`services/scoring.py`, `services/comparison.py`) that part 4 builds
on, and the practice harness over LobbyPlag's labelled pairs. The first brief's HTTP
routes, its `influence submit` command and the evidence workspace were removed on
6 October 2026. The [frozen semantic experiment](evaluation/README.md) records the lexical
baseline's failure cases and a local reranker comparison.

## Run

Use the repository's Python 3.14 and uv toolchain. From the repository root:

```sh
uv sync --directory backend --locked
make dev-backend
```

The API is at `http://127.0.0.1:8000`, interactive documentation at `/docs`, and the
machine-readable contract at `/openapi.json`. `/health` reads no data. The view routes
read the law bundles that `make atlas` and `make lineage` write under `data/laws/`
(`INFLUENCE_DATA_ROOT` points elsewhere, for example at `mock-data/`); a law without a
view answers 404 with the command that builds it. `make up` serves the same API from a
container (root README).

`INFLUENCE_LOG_LEVEL` sets how much the API logs: `debug`, `info` (the default), `warning`,
`error` or `critical`, in any case. It applies to the API's own `influence.*` loggers
(one line per record on stderr: time, level, logger name, message) and to uvicorn's
startup and access loggers; other libraries keep Python's default, WARNING. The app reads
it when it is created, so any other value stops startup with an error that names the
variable and the accepted values, rather than running at a level nobody chose.

The local frontend origins `http://localhost:3000` and `http://127.0.0.1:3000` are allowed
by CORS for GET requests; the explorer normally reaches the API through Next.js's
same-origin proxy and needs no CORS. There is no authentication: every route reads public
data and writes nothing.

The practice loop's LobbyPlag snapshot (`make fetch-lobbyplag`, into `data/lobbyplag/`) is
read by the practice commands only, never by the API.

## Setup Command (Atlas Part 1 Inputs)

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

## Collect Command (Atlas Part 1)

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
[Setup Command](#setup-command-atlas-part-1-inputs).

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

## Atlas Command (Parts 3 to 7)

`influence atlas <law>` (`make atlas LAW='2021/0106(COD)'`) runs `influence collect`, then
`services/pipeline.py` over the collected bundle, then writes `atlas.json` beside it. It
also writes `coordinated.json`, the law's coordinated amendments (clusters of near-identical
inserted wording tabled by Members of different political groups, `services/coordinated.py`,
the same code and file as `influence coordinated <law>`), and prints one line with how many
clusters span political groups. Both files are built before either is written, and the view
is written last, so a listed law has the clusters of the same run beside it. The pipeline
adds no logic of its own; it calls each part's code in order:

| Step | Code | Writes into the view |
| --- | --- | --- |
| Asks | `asks_from_passages`: one ask per consultation passage, `extraction_method="passage-v0"`; `direction` read from the passage's quoted instructions (`assessment.requested_direction`), unknown for prose | asks the shown links reach |
| Candidates | `services/retrieval.py` BM25, top 5 passages per amendment's changed words | (not shown) |
| Verdicts | `services/assessment.py` on every candidate, with 8-word quotations of the proposal masked out of prose (`services/masking.py`, `QuotedLaw`, indexed once per law) | links that are `published`, `unconfirmed` or `contradicted` |
| Outcomes | `services/outcomes.py` for each ask's strongest published or unconfirmed link | outcomes |
| Graph | `services/atlas_graph.py` from the same records as the bundle | `snapshot` |
| Counts | `services/atlas_analysis.py`, final-act rows in its order | `rankings` |
| Mode labels | `services/modes.py` from the law's typed coverage and status | `modes` |

The view keeps every record the shown links reach and nothing else. Nothing serves it over
HTTP since 6 October 2026: `make forecast`, `make directions`, `make report`, `make batch`
and the blind audit read `atlas.json` from disk.

`modes` holds the mode labels of [the plan, section 6](../docs/plan.md#6-typed-partial-results):
what a gap in the law's layers means for a reader. Each is derived from the coverage rows
part 1 recorded and from the law's status, never from an empty list:

| Label | Applies when |
| --- | --- |
| `Contextual evidence, not textual` | The asks layer is `missing`, `not_collected`, `not_applicable`, has no row, or counted zero |
| `No amendment stage` | Both the committee and the plenary amendment layers are `missing` or `not_applicable`, or counted zero. A layer that is `not_collected` is unknown and does not count as absent |
| `Negotiation in progress` | The law's status is `ongoing` and its final act was not read (the layer is not `complete`, `partial` or `stale`) |
| `Partial amendment coverage` | Either amendment layer is `partial` or `stale` |

The plan's fifth label, "Not analysed (DE)", needs per-passage language counts the view does
not carry yet and is not derived.

The API reads the same data root as the command (`INFLUENCE_DATA_ROOT`, default the
repository's `data/`; `create_app(atlas_data_root=...)` in tests).

**Limits, stated in every view.** Ask extraction is a stand-in: every passage is one
ask, so outcome counts count passages, not distinct requests. Only copied-tier links are
published, at part 4's thresholds calibrated on LobbyPlag (one 2013 law), and their precision
on new laws is unaudited; the sentence is built from `assessment.py`'s revision and tiers.
Outcomes are traced only for asks with a published or
unconfirmed link; rankings count only outcomes traced through published links. Only quoted instructions carry a direction, so part 4's same-direction and
opposite-direction checks do not run on prose asks, and each prose link says so; when the
proposal's text is missing, the view says its quotations were not masked. Tested offline (`tests/test_pipeline.py`, `tests/test_modes.py`, and
`tests/test_coordinated.py` for the clusters route). One real run (`measured`,
3 October): `influence atlas '2021/0106(COD)'` on the AI Act finished in 310 s with the
public downloads already cached (no uncached timing, one law only), and its `rules-3` view
published 0 links (859 unconfirmed, 82 contradicted); see
[implementation status](../docs/implementation-status.md).

**Stale calibration artifacts.** `evaluation/link-calibration.json` (`link-calibration-v1`)
and `evaluation/dense-meaning.json` (`dense-meaning-v1`) predate three practice-loop fixes:
the reworded tier is now chosen and reported on its own band below the copied cut, identical
inputs from different organizations now share one test fold, and the judge's and embedder's
input cuts are counted. Their numbers (including the 0.32 reworded cut) are not current
until regenerated: `make fetch-lobbyplag`, then `python -m influence.practice.calibrate` and,
with the models fetched, `make evaluate-dense` (commands in the module docstrings). The fold
change also touches every other fold-based result (`practice-results.json`,
`calculation-*.json`): rerun `python -m influence.practice` and `benchmarks/calculation_plan.py`.

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
- `ETag`: a strong tag hashed from the installed package version and each view file's
  slug, size and modification time in nanoseconds. For the list it covers every view, so
  it changes when any view is added, rewritten or removed.
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

## Coordinated Amendments Command (Part 3)

`influence coordinated <law>` (`make coordinated LAW='2021/0106(COD)'`) collects the law
as `influence collect` does, then lists the amendments whose inserted wording is
near-identical and which were tabled by Members of different political groups. Such a
cluster is a candidate for a shared outside draft; it is not proof of one. It reads only
what part 1 took from Parltrack: the law's amendments and their Members.

| Step | Code | Rule |
| --- | --- | --- |
| The change | `services/scoring.changed_spans`, the diff parts 3 and 4 use | Only inserted wording is compared, quoted from `new_text` with exact offsets. An unknown original is read as empty |
| Comparable | `MIN_INSERTED_WORDS = 12` | Shorter insertions and deletions are counted as `too_short`; amendments over the diff's bounds (800 tokens a side) as `not_comparable` |
| Similar | `SHINGLE_WORDS = 5`, `SIMILARITY_THRESHOLD = 0.8` | Jaccard similarity of the two sets of five-word runs; pairs are found through an inverted index |
| Cluster | union-find over similar pairs | A chain joins A to C through B; `min_similarity` reports the least similar pair |
| Across groups | `cross_group` | Two members with no author in common and no political group in common, both groups known |

The output is `data/laws/<procedure>/coordinated.json` (`schemas/coordinated.py`,
`CoordinatedView`): the parameters, the counts, every cluster with its members, and the
limitations. Clusters that span groups come first. The command prints the first ten.

**Measured** (3 October 2026; Windows 11 laptop, Intel Core Ultra 7 258V, 8 logical CPUs
and 15 GB in WSL2, Python 3.14.7; `--no-attachments`, HTTP answers cached, a fresh law
folder). Wall time is the whole command, of which collect is the first figure:

| Law | Amendments | Compared | Clusters | Span groups | Collect | Whole command | Peak memory |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AI Act, 2021/0106(COD) | 5,660 | 2,967 | 269 | 83 | 25.4 s | 29.2 s | 228 MB |
| Digital Services Act, 2020/0361(COD) | 6,476 | 3,299 | 508 | 80 | 23.8 s | 27.3 s | 236 MB |
| Data Act, 2022/0047(COD) | 2,437 | 1,325 | 173 | 72 | 22.4 s | not kept | not kept |

**Limits.** The three parameters are proposed, not calibrated: no labelled set of
coordinated amendments exists, and nobody has audited a sample of these clusters. A
Member's group is the one of their latest spell in Parltrack's dump, so a Member who
changed group after tabling is listed under the later group (the AI Act's list shows
"Patriots for Europe Group", founded in 2024, on 2022 amendments). Members also agree
wording among themselves, so a cluster shows shared wording, not its author. The clusters
are not yet in `atlas.json` or the explorer.

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
null, never zero. `python -m influence.practice.lineage_review` draws a seeded uniform
sample of phrases for two readers to label. Nothing in this view has been audited yet.

## Channels Command (Part 7, HOW)

`influence channels <law>` (`make channels LAW='2021/0106(COD)'`) collects the law as
`influence collect` does, then counts the channels the law was lobbied through, from the
collected records alone, and writes `data/laws/<procedure>/channels.json`
(`schemas/channels.py`, `ChannelsView`, method `channels-1`). It reads no link, so the
counts exist for any law before part 4 has verified anything. Every count sits beside its
denominator; every count describes the record (a channel associated with the law), never a
cause.

| Section | What it counts | Source |
| --- | --- | --- |
| `consultation` | Feedback per Have Your Say publication (one consultation stage), with the publication's type code from the Have Your Say index (`PROP_REG` is feedback on the proposal); submitters by actor kind and register category; organisations carrying a register ID, of all organisations | `documents.jsonl`, `passages.jsonl`, `actors.jsonl`, `data/catalog/hys-index.jsonl` |
| `timing` | Feedback dated before or on/after `proposed_on`; amendments tabled before or on/after `proposed_on` and `completed_on`; undated records and records with no reference date counted apart | `law.jsonl`, `documents.jsonl`, amendments |
| `meps` | Amendments by stage, committee and political group of the tabling Members (a co-signed amendment counts once per group); amendments with no known author or no known group; the 20 Members who tabled the most | amendments, MEP actors |
| `coalitions` | Amendments co-signed by several Members, and across groups; part 3's coordinated clusters (`find_coordinated`) and how many span groups | amendments, MEP actors |
| `votes_and_meetings` | Part 1's coverage rows for `votes` and `meetings`, status and reason; no count is shown because neither is collected yet | `law.jsonl` |

When the Have Your Say index is not built, publication types are `null` and
`publication_type_gap` says why. Organisations whose submissions share wording are not
counted (comparing every pair of submissions is too slow for a live run); the file's
`limitations` list this and the other gaps. **Not measured**: no real law has been run
through this command yet; it is tested offline on fixture laws only.

## Directions Command (Part 7, TOWARDS)

`influence directions <law>` (`make directions LAW='2021/0106(COD)'`) collects the law as
`influence collect` does, then labels which way each amendment moves the law and writes
`data/laws/<procedure>/directions.json` (`schemas/directions.py`, `DirectionsView`). The
rules (`services/direction.py`, method `direction-rules-1`) are fixed English cue lists
over the diff part 4 uses, applied in this precedence; the first that fires decides:

| Order | Direction | Fires when |
| ---: | --- | --- |
| 1 | `delete` | The new wording is empty or Parltrack's `deleted` marker, or the edit inserts nothing and removes at least half of the original |
| 2 | `unknown` | The original wording is unknown (`original_unknown`) or over the diff's bounds (`over_long`) |
| 3 | `keep` | Both sides hold the same words |
| 4 | `exempt` | An exemption phrase occurs more often after the edit: "shall not apply", "exempt", "derogation", "excluding", "with the exception of", "except" |
| 5 | `delay` | "postpone", "defer", "transitional period" or "grace period" is added, or a year or period is replaced by a later or longer one |
| 6 | `stricter` / `weaker` | Obligation cues added minus removed ("shall", "must", "required", "at least", "minimum", "prohibit", "ban", "may not" against "may", "can", "optional"; a removed exemption counts as stricter); a tie falls through |
| 7 | `add` | The edit only inserts wording |
| 8 | `other` | Anything else |

So "shall" to "may" is weaker, and an inserted "not" that makes "shall not apply" is an
exemption, not a stricter "shall". Part 4 keeps its narrower `amendment_direction` for its
same-direction signal; changing it would change published scores without practice-loop
evidence.

The file holds the counts for every amendment, by stage, by political group (an amendment
co-signed across groups counts once in each; amendments with no author of known group are
`without_group`) and for the twenty Members who tabled most, plus one example amendment
per direction with the deciding wording quoted at exact offsets. Actor directions are read
only through the published links of the law's `atlas.json`, one count per link: without
that view `actors_status` is `no_atlas_view`, and with no published link it is
`no_published_links`, each with its reason. Unconfirmed and contradicted links are never
used. Run `make atlas` first to get actor directions.

**Limits.** Rule-based and English-only; a direction describes an edit, not the stance of
whoever tabled or asked for it, and counts are not causes. Tested offline
(`tests/test_direction.py`, including a table of edits per rule); not yet run on real data,
timed, or audited against human labels.

## Blind Audit Commands (Gate 7)

The audit measures how often the links we publish are right. Two people read the same
links apart, without seeing what the pipeline concluded, and the score is reported with
its uncertainty. Labels are stored under `data/audit/` only: nothing here writes to a
law's bundle or `atlas.json`, and no threshold or link is changed by an audit result.

1. `influence audit sample <law> --seed N [--size 40] [--status published|unconfirmed]
   [--tier copied|reworded]` (`make audit-sample LAW='2021/0106(COD)' SEED=N`) reads the
   law's `atlas.json` (name it by procedure number or slug; run `make atlas` first) and
   draws a seeded sample with `services/audit.py`'s `draw_sample`: spread over (law, tier)
   in proportion to size by largest remainder, every stratum given at least one seat, a
   pure function of the links and the seed. It writes, under
   `data/audit/<slug>/<status>[-<tier>]-seed<N>-n<size>/`:
   - `reader-a.csv` and `reader-b.csv`, identical blind sheets with an opaque item ID
     (numbered in a seeded shuffle), the actor, the ask's quote, date and source URL, the
     amendment's ID, provision, old and new wording, tabling date and source URL, and
     empty `verdict` and `note` columns. No link ID, score, tier or status.
   - `key.json`, kept from the readers: each item's link record, tier, score, status and
     stratum, the seed, the size and the population it was drawn from.

   An existing sample directory is refused, so a rerun cannot overwrite filled sheets.
2. Each reader fills `verdict` with `yes` (the ask's wording or request reached this
   amendment), `no`, or `unsure`, plus an optional note, without talking to the other.
3. `influence audit score <dir>` (`make audit-score DIR=data/audit/<slug>/<sample-id>`)
   checks that each sheet lists exactly the key's items and only yes, no, unsure or blank,
   then writes `audit-result.json` and `audit-summary.md` beside the sheets: per stratum
   and overall, the links both readers marked correct, both marked incorrect, the splits
   and the blanks, and precision with its Wilson 95% interval (`audit.summarise`). A link
   is correct only when both readers say yes: `unsure` counts as no, a split counts as
   incorrect, and a blank leaves the link unlabelled (counted in neither, and reported).
   The result says whether the overall lower bound reaches the copied-like floor of 0.90.

**Unconfirmed sample: the proposed re-scope.** Plan gate 7 audits published links; the
last real AI Act run published none, so the plan carries a **proposed, not adopted**
re-scope: audit a sample of *unconfirmed* prose links to set the prose threshold.
`--status unconfirmed` supports it and every output says so. Its score adds, for support-
score cuts 0.05 to 0.95 in steps of 0.05, the sampled links at or above each cut, their
precision and Wilson lower bound, and the lowest cut whose lower bound reaches 0.90. That
cut is a proposal only: a person decides whether the threshold moves (recorded in the
plan), and the pipeline then rebuilds the graph. With 40 links the bound is wide: even
30 of 30 correct bounds precision at about 0.886, so reaching 0.90 needs about 35 links,
all correct, at or above the cut.

**Limits.** Tested offline on the invented fixture (`tests/test_audit_sheets.py`:
blindness, determinism by seed, agreements and splits, the threshold grid, invalid
sheets). No real sample has been drawn or read yet; no precision is measured.

## Forecast Command (Part 7, NEXT)

`influence forecast <law> [<law> ...]` (`make forecast LAW='2021/0106(COD)'`, more laws in
`ARGS`, each quoted) answers "which asks will land next?" from the views `make atlas` has
already written; it fetches nothing. Each law is named by slug, procedure number, CELEX,
COM reference, common name or title, and must have an `atlas.json`. It writes
`data/laws/forecast.json` atomically (`schemas/forecast_view.py`, `ForecastView`):
`laws` (per law: status, whether it is a target, asks, training examples, forecasts and
excluded counts by reason), `validation`, `fallback_rule`, `forecasts` (`Forecast`
records) and `limitations`.

- **History** (`services/forecasting.py`): every ask of every completed law whose final-act
  outcome is decided: full or partial is a win, not observed a loss, unknown is left out.
  Features are the law's first subject, the asking actor's kind and how many amendments
  carry the ask through a published or unconfirmed link. An example is kept only when the
  ask and each of those amendments are dated before the law's completion date
  (`Example` refuses any other).
- **Targets**: the undecided asks of the named laws that are still open (`ongoing` or
  `unknown`). A named completed law only adds history; a withdrawn one has nothing to
  forecast.
- **Validation** (`services/forecast.py`): rolling time splits ordered by completion date,
  never one law on both sides, against the prevalence baseline. A probability is published
  only with three tested splits, a hundred test asks and a Brier score at least 5% better
  than prevalence. Otherwise every forecast is a scenario with no score, and its reasons
  give the counts of laws, splits and test asks that fell short. With the few laws built
  for the demo, that is the expected result.
- **Fallback rule**: the plan's labelled fallback, "the rapporteur's draft includes the
  ask", is reported as `computable: false`. Parltrack gives the rapporteurs' names, but
  the collect step fetches no draft report text, so no rule score is computed rather than
  one approximated from other data.

**Limits.** The view keeps only asks with a link, so the history holds no ask that no
amendment carried. Tested offline (`tests/test_forecasting.py`: scenario and probability
paths, leakage refusal, every exclusion reason, law naming, the command end to end); not
yet run on real laws or timed.

## Batch Command (Plan Gate 9)

`influence batch` (`make batch ARGS=...`) runs collect and the per-law steps over many
laws, for the brief's "all of Europe from 2019". It adds no analysis of its own: each step
is the service its own command calls, so a law's files are the same whichever command
wrote them.

```console
make batch ARGS="--laws 'AI Act,DSA,2021/0106(COD)'"
make batch ARGS='--since 2019 --with-amendments --limit 50'
make batch ARGS="--laws 'AI Act' --steps atlas,coordinated,channels,lineage,directions --attachments"
```

- **Selection.** `--laws` takes comma-separated procedure numbers, CELEX, COM references,
  common names or titles, resolved as `collect` resolves them; a name that resolves to
  nothing is recorded as a failed law. `--since YEAR --with-amendments` scans the
  committee and plenary amendment dumps once (about a minute) and selects every procedure
  of the dossiers catalog with an amendment tabled on or after 1 January YEAR, most
  amended first; `--limit N` keeps the first N.
- **Steps.** Collect runs first, without attachments unless `--attachments` is given.
  `--steps` picks from `atlas,coordinated,channels,lineage,directions` (default
  `coordinated,channels,lineage,directions`, which read Parltrack and the bundle and take
  seconds; `atlas` takes minutes a law and is opt-in). Steps run in that order, so
  `directions` reads the atlas view built just before it.
- **Resume.** A law with a published collect manifest is not collected again, and a step
  whose output file names that manifest's `run_id` is skipped; `--refresh` collects again
  and redoes every step. A law or step that fails is recorded with its error and the batch
  goes on; the exit status is 1 unless every law completed.
- **Output.** `data/laws/batch.json` is written atomically after every law, so an
  interrupted batch keeps what it finished. It holds the selection, the steps, and per law
  the query, procedure, title, status (`complete`, `partial`, `failed`), collect `run_id`,
  error, seconds, amendments, each step's status (`done`, `reused`, `skipped`, `failed`)
  with its seconds and error, and the collect coverage rows (layer, status, count). Its
  `banner` counts laws selected, attempted, complete, partial and failed, the amendments
  covered, how many laws lack each layer, how many each step failed on, the hardware, and
  the start and finish times (`finished_at` is null until the last law is done).

**Limits.** Collect scans the amendment dumps once per law (plan §5), so a batch over
every procedure since 2019 takes hours; it has not yet been timed on real data. A law
collected earlier is reused even when collected with other settings; use `--refresh`
after a code or dump change. Tested offline (`tests/test_batch.py`).

## Report Command (Part 8)

`influence report <law> [<law> ...]` (`make report LAW='2021/0106(COD)'`; several laws are
separated by commas, `LAW='AI Act, 2022/0140(COD)'`) writes the public report
(`services/report.py`) to `data/laws/report.md`, atomically, and prints each section's
headline, the link sample and the path. It collects and computes nothing: it reads the
collected bundle (for actors' declared register spend and source URLs) and the files the
other commands wrote, `atlas.json`, `coordinated.json`, `channels.json`, `directions.json`
and `lineage.json` under `data/laws/<procedure>/`, plus `data/laws/forecast.json` when
`influence forecast` has written it. A law is named by procedure number, slug, CELEX, COM
reference, title or common name, matched only against laws already collected.

The Markdown holds a coverage block (layers, gaps, run IDs, files not run, built from an
older run or invalid), then WHO, WHAT, TOWARDS, HOW and NEXT, each with a headline in
"N of M" form, a named actor or law, evidence (the file and field, record IDs) and one
limitation; wins beside declared spend with ranks, for actors with at least 3 assessed asks
and a declared cost (or the count saying none qualify); links side by side; and methods and
limits (provisional thresholds, what is cut, the limitations the view recorded).

**Links side by side.** `--links N --seed S` (defaults 3 and 20261003) draws a seeded uniform
sample of published links, and prints for each the actor, the quoted ask span, the quoted
amendment spans with the amendment ID, tabling Members and date, the final-act wording when
traced through that same amendment, and every source URL. With no published link it says
"0 published links" and shows instead a sample of lineage's verbatim adoptions (amendment to
final article), labelled as not published links. The same seed draws the same links.

A missing file is a line such as "Not run: `data/laws/2021-0106-COD/lineage.json` is missing;
run `make lineage LAW='2021/0106(COD)'`", never a zero. `--out` is resolved from `backend/`
when run through `make`. Tested offline (`tests/test_report.py`); not yet run on a real law.

## HTTP Contract

| Method and path | Result |
| --- | --- |
| `GET /health` | `{"status": "ok", "version": ...}`; reads no data |
| `GET /api/v1/lineage`, `GET /api/v1/lineage/{slug}` | The lineage views: see "Lineage View API" |

A slug without a written view answers 404 with the command that builds it; an unreadable
view answers 500 with the reason. The view routes send `Cache-Control`, `ETag` and `Last-Modified`
and answer 304 to a matching `If-None-Match` (see "Lineage View API"). Invalid parameters return FastAPI's 422 validation
response. OpenAPI defines each successful response schema.

A response body of 1,024 bytes or more (`GZIP_MINIMUM_BYTES` in `api.py`) is
gzip-compressed when the request's `Accept-Encoding` names gzip: the answer carries
`Content-Encoding: gzip` and `Vary: Accept-Encoding`, and decompresses to exactly the plain
body. Without gzip in `Accept-Encoding` the body is sent as is. Shorter bodies, such as
`/health`, the law list and a 404, and bodiless answers such as a 304, are never compressed. The AI Act's lineage view
in `mock-data/` goes from 1,262,923 bytes to 158,677 (measured 6 October 2026).

### PDF and Text Extraction

`services/documents.py` (`extract_document`) turns a PDF or UTF-8 text into numbered pages
for part 1, which reads Have Your Say attachments through it. It returns `format`,
numbered `pages` with extracted `text`, `warnings`, `character_count`, `glyphs_guessed`
and `glyphs_unresolved`. PDF ligature code points (U+FB00 to U+FB06) expand to their
letters. A ligature glyph that the PDF font maps to no character comes out of pypdf as
U+0000 (`signi\0cant`); it is restored as fi, fl, ff, ffi or ffl when the spelling appears
elsewhere in the document or a known word part covers it, and otherwise replaced by a
space. Both counts carry a warning, and Have Your Say attachments record them in
`extraction_method` (`pypdf+glyph_repair:guessed=N,unresolved=M`) and in the asks
coverage reason. The repair runs before passages are cut, so every span indexes the
repaired text. Extraction does not guess which columns are original/proposed wording or
select evidence passages.

Limits: 8 MiB of input, 100 PDF pages, 500,000 extracted characters, 2 MiB expanded
content per page and 16 MiB aggregate page streams. Oversized, invalid, encrypted or
empty documents raise `DocumentExtractionError` with a stable `code`
(`document_too_large`, `too_many_pages`, `text_too_large`, `pdf_stream_too_large`,
`invalid_pdf`, `encrypted_pdf`, `empty_document`, `invalid_utf8`); a PDF with no text is
`ocr_required`, and OCR is not performed. Multi-column and table reading order cannot be
guaranteed by PDF extraction. pypdf's context-local decompression limits contain common
expansion cases and external image conversion is disabled; these limits are not a hard
memory or CPU sandbox.

## Separation of Responsibilities

`api.py` assembles the application: CORS and the three route groups (`health`, `atlas`,
`lineage`). `routers/` declares routes and validates HTTP parameters; it contains no
matching or data-joining logic. `schemas/` defines immutable typed records. `services/`
holds the pipeline's parts, each callable without the web server, because `cli.py` (a thin
`argparse` layer) and the batch command call them directly. `repositories/` reads the
public sources (Parltrack, CELLAR, Have Your Say, the Transparency Register) and, for the
practice loop only, LobbyPlag's snapshot; none of them calls the network at request time
or writes outside `data/`.

LobbyPlag's candidate file repeats identifiers: rows with the same candidate identifier,
amendment, proposal and verification value are coalesced and conflicts are rejected
(`repositories/lobbyplag.py`), so candidate and verified counts refer to unique records.
Its historical `verified` values are labels for the practice loop and are never supplied
to a scorer.

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
```

**The cache is not an optimisation.** A second identical request never leaves the
machine, so a parser can be re-run at 17:00 without re-downloading 400 PDFs, and a rate
limit plus a User-Agent carrying a contact address keeps the team from being blocked
mid-event. `fetching.py` is the only module that touches the network: two requests per
second, standard library only, and a non-2xx response raises instead of being cached, so
a source that returns 503 at 10:00 and works at 11:00 is not remembered as broken.

**The records a law produces** are the typed models of `schemas/atlas.py` (`LawRecord`,
`SourceDocument`, `Passage`, `Amendment`, `ArticleVersion`, `Actor`, and so on), written as
JSON Lines by the collect command (see "Collect Command" above) and read back by every later
part. They replaced this layer's first row models and per-law manifest on 6 October 2026:
the `RunManifest` that `collect` publishes last plays the manifest's role, and every record
carries its source document, retrieval date and hash, because the jury picks edges at random
and asks to see the original. JSON Lines rather than CSV, because legal text contains every
delimiter, and rather than Parquet, because Parquet needs a new dependency (pyarrow) that the
supply-chain policy has not cleared.

**Entity resolution** is the join nothing else can do: only the register carries a
registration identifier, consultation submissions carry free text, and roughly half of the
free-text names do not use the register's official spelling, so a join on the raw name looks
right and is wrong. `names.py` keeps the normalisers (`tokenise`, `normalise`,
`token_set_ratio`, which strip case, punctuation, legal suffixes and filler words) and the
0.90 fuzzy threshold; `services/actors.py` (part 2) is the resolver that applies them and
records which layer fired, keeping an ambiguous or unresolved name visible rather than
guessing.

## Verification

Run `make check-backend` for locked dependencies, Ruff, strict basedpyright, unit/API
tests, gate probes, and 100% line and branch coverage. Run `make check` for the entire
repository, including frontend build and vulnerability audits. Tests use small synthetic
snapshots and do not require the downloaded public corpus or network access. tbd remains
the work tracker; this README describes the delivered backend.

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

## Fitted Signals and Local Model Evaluation

`services/signals.py` (rarity, alignment, direction and legal cues), `services/ranking_signals.py`
(law-local background and mutual ranks) and `services/calibration.py` (a standardised,
L2-regularised logistic combiner fitted on grouped folds, with a Wilson-bound threshold
selection) are the development evaluation of part 4's fitted signals. They are measured by
the benchmark below, not called by the live `influence atlas` path, whose assessor is the
rule-based `services/assessment.py`. The `calculate_links` composition that once bound them
into a publication policy was removed on 6 October 2026 as dead code (nothing but its own
tests called it); the [calculation design and plan-coverage handoff](../docs/design/calculation-handoff.md)
keeps its formulas and evidence gates as the record of that design. The
[isolated model runtime](models/README.md) gives reproducible local Qwen/E5 embeddings,
DeBERTa NLI inference, measured retrieval comparisons and failed legal diagnostics.
No paid API or new application dependency is required.

Run the grouped development comparison from the repository root:

```sh
uv run --directory backend --locked python benchmarks/calculation_plan.py \
  --data /absolute/path/to/data/lobbyplag \
  --out /absolute/path/to/calculation-development.json
```

To include model features, first prepare and run the models as described in their
README, then pass `--semantic <semantic-pairs.json>`, `--judge <judge-pairs.json>` and
`--model-inputs <inputs.json>`. Both artifacts must bind the same exact prepared-input
file and current source hashes. The evaluator rejects incomplete coverage or missing
scores instead of inserting zeros. Its output retains all variants, five fitted models
per variant, paired out-of-fold scores, settings, hashes and threshold diagnostics.
Those pooled diagnostics cannot serve as the cutoff for a separately refitted model.

## Lineage in the Explorer (Experiment)

Two scripts in `benchmarks/` feed the existing explorer with lineage instead of part 3's
BM25 verdicts. Both read a collected law (`make collect LAW='AI Act'`).

```sh
cd backend
# Reworded origins: BM25 shortlists passages per adopting amendment, Jev judges each pair.
uv run --locked python benchmarks/lineage_jev.py --law ../data/laws/2021-0106-COD            # dry run, no call
uv run --locked python benchmarks/lineage_jev.py --law ../data/laws/2021-0106-COD \
  --execute --env-file .env --max-cost-usd 1                                                   # calls Jev
# Verbatim + Jev links -> data/laws/<slug>/atlas.json, in the atlas-view-1 shape.
uv run --locked python benchmarks/lineage_view.py --law ../data/laws/2021-0106-COD
```

`--env-file` names a file holding `TYPESAFE_API_KEY` (never committed); without it the key is
read from the environment. Answers are cached under `data/laws/<slug>/lineage-jev/`, with the
cumulative charge in its `ledger.json`. Jev links are always `unconfirmed`: no publication
threshold on real consultation prose has been audited. See `docs/implementation-status.md`.
