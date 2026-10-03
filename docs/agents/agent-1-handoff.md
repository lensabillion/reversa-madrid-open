# Agent 1 Handoff: Data and Integration

Written 3 October 2026, 14:15 CEST, for the session that continues
[the Agent 1 assignment](agent-1-data-and-integration.md). Everything below is on the
branch `feat/collect-law` (draft PR
[#26](https://github.com/lensabillion/reversa-madrid-open/pull/26)) unless it says
otherwise. Tags: `measured` (we ran it), `reported` (a sub-agent's report, not rechecked
by the lead), `not verified`.

## Start Here

1. `git fetch && git checkout feat/collect-law`.
2. Read this file, then `backend/src/influence/schemas/atlas.py`.
3. Run the backend gate (commands in [This Laptop](#this-laptop)). It fails today; the
   exact failures are in [Gate State](#gate-state-of-the-snapshot).
4. Fix the gate, then build the collect service (see [Next Steps](#next-steps-in-order)).

## Branches and Pull Requests

| Branch | Holds | State |
| --- | --- | --- |
| `feat/atlas-contracts` | `schemas/atlas.py` (schema `atlas-1`), fixtures in `backend/tests/fixtures/atlas/` | PR [#25](https://github.com/lensabillion/reversa-madrid-open/pull/25), open, all nine CI checks green (`measured`). **Agents 2 and 3 build against commit `f1525db`.** Needs the owner's merge |
| `feat/extraction-foundations` | The cloud session's fetcher, HTTP cache, layout, name matching and probe CLI, with `main` merged in | Pushed, no PR. 256 tests, 100% branch coverage (`measured`). It is contained in `feat/collect-law`; open its own PR only if the owner wants it reviewed separately |
| `feat/collect-law` | Both of the above merged, plus all collection work | Draft PR #26. A work-in-progress snapshot: the gate does not pass yet |

Nothing has been merged to `main` by this session. The stack to aim for: #25 first, then
#26 rebased on `main`.

## What Is Done

| Module | What it does | Verified |
| --- | --- | --- |
| `schemas/atlas.py` | The shared record contracts: `LawRecord`, `LayerCoverage`, `SourceDocument`, `DocumentText`, `SourceSpan`, `Passage`, `Amendment`, `ArticleVersion`, `Actor`, `Ask`, `Candidate`, `LinkAssessment`, `Outcome`, `PublicPosition`, `Forecast`, `GraphSnapshot`, `RunManifest`; canonical ID builders | 28 tests, 100% branch coverage, CI green on #25 |
| `tests/atlas_fixture.py`, `tests/fixtures/atlas/` | An invented two-law bundle (procedures dated 2099) covering supported copy, opposite request, short shall/may edit, ambiguous actor, missing date, missing final act, partial outcome. The `.jsonl` files are generated: run `python tests/atlas_fixture.py` after a contract change | A test fails when files and builder differ |
| `services/law_query.py` | Recognises a procedure reference, CELEX or COM number by shape and normalises it; ranks catalog titles for free text; returns up to three choices when the best two are within 3%; an exact alias wins | 100% branch coverage (`measured`) |
| `extraction/records.py` | Atlas records as JSON Lines. `StageStore` writes each stage under `data/laws/<slug>/stages/<stage>/<input hash>/` with a receipt, reuses a stage only when its files still match their hashes, and publishes `manifest.json` last | 100% branch coverage (`measured`) |
| `repositories/parltrack.py` | Streams the Parltrack dumps: procedure catalog, committee and plenary amendments as `Amendment`, MEPs as `Actor`, the dump as `SourceDocument` | 29 tests, 100% branch coverage (`measured`); real-data numbers below (`reported`) |

| `repositories/register.py`, `services/actors.py` | Streams the Transparency Register export to `Actor` records; resolves an identity per organisation (`rev-1vxz`) | 45 tests, 100% branch coverage of both (`measured`); real-data numbers below (`reported`) |

### Register and Actor Resolution on Real Data (`reported` by its sub-agent)

- 17,897 register entries in 5.5 to 7.1 s at constant memory; export dated
  2 October 2026. The file declares XML 1.1 and contains illegal control-character
  references, so it is parsed line by line with those references replaced by a space.
- Declared lobbying cost is always a band: 11,521 entries have a usable midpoint; 5,025
  (mostly NGOs) declare a total budget instead, kept on `RegisterEntry.total_budget_eur`
  and not copied to the `Actor`.
- All 304 AI Act submissions (Have Your Say publication 14488) resolve in 0.12 s: 173 by
  register ID, 30 by exact name, 4 acronym proposals, 6 fuzzy proposals, 79 unresolved,
  12 citizens aggregated into one actor. 25 submissions cite a register ID absent from
  today's export; they keep `actor:tr:<id>` with a note in `category`.
- Name-only check on the 148 rows whose ID is in the register: 71 exact merges, all
  correct; 38 proposals, all containing the true entry; 39 with no candidate (one-word
  names and names contained in a longer register name are not proposed).

Decisions the next session must take on it:

- **A rule added beyond the brief:** an exact normalised-name match is accepted only when
  both names use "Europe/European/EU" equally often, because the normaliser drops those
  words and "Fair Trials" (UK) was merging into "Fair Trials Europe" (Belgium). Otherwise
  it becomes a proposal. Confirm or revert.
- The citizens aggregate carries `resolution="unresolved"` because the contract has no
  better value; `resolution_summary` counts it under its own `citizens` key. Adding an
  `aggregate` value to `ResolutionMethod` would be a schema change (bump `atlas-1`).
- Country: the register writes English names, Have Your Say ISO-3; register actors carry
  ISO-3.

### Parltrack on Real Data (`reported` by its sub-agent)

- Catalog: 23,885 dossiers give 20,464 procedures in about 10 s; 3,421 dossiers are
  Commission documents (`COM(…)`, `SWD(…)`), not procedures, and are skipped and counted.
  Every real procedure reference matches the contract's `PROCEDURE_PATTERN`.
- Committee amendments: AI Act `2021/0106(COD)` 4,852; DSA `2020/0361(COD)` 5,901; EHDS
  `2022/0140(COD)` 2,458. All three match the research counts. About 5 s per law.
  Plenary: 808, 575 and 557. Every record validates as `Amendment`; IDs are unique.
- 171 MEP actors for the AI Act's committee authors in 2.1 s.

Decisions the next session must take on it:

- **Insertions arrive as unknown.** Parltrack omits `old` for most insertions, so they
  get `old_text=None`; about 97% of those say "(new)" in `target_provision`. Treating
  "no `old` and location ends in (new)" as `""` is a small change in `_wording`. Agent 2
  needs to know which it is: decide, then tell them.
- **`Amendment.document_id` does not join to a `SourceDocument`.** Amendments point at
  the Parliament document (`doc:parltrack:PE704.585v01-00`); the only source document is
  the dump (`doc:parltrack:ep_amendments`). Emit one `SourceDocument` per Parliament
  document, or point amendments at the dump.
- `political_group` is the MEP's current or latest group, not the group at tabling time.
- EHDS has no `celex_final` or lead committee in the Parltrack dossier: take the final
  act from CELLAR.

## In Flight When This Was Written

Two sub-agents were still writing these. Their files are committed as they stood at
14:15; a sub-agent does not survive the session, so treat each as unfinished.

| Files | Job | State at the snapshot |
| --- | --- | --- |
| `repositories/cellar.py` (655 lines); request headers and HTTP 300 support in `extraction/fetching.py`, `tests/extraction_fixtures.py`, `tests/test_extraction_network.py` | Procedure to CELEX by SPARQL; fetch proposal and final act by content negotiation; split XHTML into `ArticleVersion` | `fetching.py` at 100% coverage. **`cellar.py` had no test file when the gate was run (0% coverage);** a `tests/test_cellar.py` appeared minutes later and is committed but has not been run by the lead. Not run on real data by the lead |
| `repositories/hys.py`, `services/passages.py`, `tests/test_hys.py`, `tests/test_passages.py` | Have Your Say index by COM reference, feedback paging, attachment PDFs to text, passages with code-point offsets | Both modules at 100% coverage, but 1 failing test (`test_feedback_becomes_a_source_document_and_its_text`), 4 type errors in `tests/test_hys.py`, and Ruff errors in `tests/test_passages.py`. The index crawl had not written `data/catalog/hys-index.jsonl` |

The briefs the sub-agents were given (rules, expected functions, what to measure) are
summarised in [Connector Specifications](#connector-specifications) so the work can be
finished or checked without them.

## Gate State of the Snapshot

Run at 14:10 on the working tree that became this commit (`measured`):

```text
ruff format --check src tests   -> 87 files already formatted
ruff check src tests            -> 8 errors, all in tests/test_passages.py (RUF001, RUF007)
basedpyright                    -> 4 errors, all in tests/test_hys.py (untyped lambda)
pytest --cov                    -> 458 passed, 1 failed (tests/test_hys.py); coverage 90%
                                   (repositories/cellar.py 0%, every other module 100%)
```

## Next Steps, in Order

1. **Make the gate pass**: write `tests/test_cellar.py` (offline, fake fetcher, trimmed
   real XHTML and SPARQL JSON) to 100% branch coverage; fix the Have Your Say test, the
   four type errors and the eight Ruff errors.
2. **Check each connector on real sources** and record the numbers here: CELLAR for the
   AI Act (final `32024R1689`, expect 180 recitals and 113 articles; proposal
   `52021PC0206`, which answers HTTP 300 and needs the `DOC_1` stream), DSA, a directive
   and an open procedure; Have Your Say publication 14488 (expect 304 items, 187 with a
   Register ID, 259 with attachments), publication 25429 (expect the typed
   "unavailable"), register entry count and resolution counts by method.
3. **`services/collect.py`**: `parse_query`, resolve to a procedure through the Parltrack
   catalog and CELLAR, then run stages through `StageStore`: metadata, law texts,
   amendments, asks (feedback, attachments, passages), actors. Fill
   `LawRecord.coverage` with the statuses of plan §6 (a failed optional source is a
   labelled gap; an unresolvable procedure, or no amendments and no asks, stops the run).
   Publish the `RunManifest` only after every output validates.
4. **`influence collect <query>`** on the existing CLI (`backend/src/influence/cli.py`),
   then thin atlas routers in `api.py`. One service, two adapters.
5. **Plan gate 1 on real sources**: the AI Act counts above, then DSA and a procedure not
   used in development with no code change; cached and uncached times with hardware.
6. **Alias table** for common names ("AI Act", "DSA", "CSDDD"), each checked against the
   catalog before it is committed; a law missing from it must still resolve.
7. **One contract**: retire the row models in `extraction/tables.py` and
   `extraction/manifest.py` that `schemas/atlas.py` replaces, and move
   `extraction/names.py`' `ActorIndex` users to `services/actors.py`.
8. Hand Agents 2 and 3 real records: branch, schema version, paths, commands, counts.
9. `rev-0who` batch over 2019+ procedures, `rev-p61s` fresh-checkout rerun, `rev-nzqr`
   release preparation (the licence itself is the owner's decision D6).

## Connector Specifications

Common rules: every HTTP request goes through `extraction.fetching.CachedFetcher`
(identity, 0.5 s rate limit, cache under `data/cache`); no new dependency; streaming
parsers; unknown stays `None`; a missing source is a typed gap, not a crash; private
individuals (`userType == "EU_CITIZEN"`) are counted under `CITIZENS_ACTOR_ID` and never
named; tests are offline with fake fetchers and reach 100% branch coverage of the module.
Endpoints are in [the data-sources research](../research/influence-atlas-2026-10/data-sources.md).

- **CELLAR** (`repositories/cellar.py`): `resolve_celex(fetcher, procedure_id)` through
  the SPARQL endpoint (procedure URI `procedure/YYYY_N`, number without zero padding),
  returning every candidate when several final acts come back rather than picking one;
  `fetch_act(fetcher, celex)` with `Accept: application/xhtml+xml` and
  `Accept-Language: eng`, following the `DOC_1` stream on HTTP 300 and returning a typed
  "missing" on 404; `split_provisions(...)` to `DocumentText` and `ArticleVersion`
  (recitals, articles, numbered paragraphs), returning zero provisions with a reason when
  the markup is not recognised. Final acts and proposals use different markup.
- **Have Your Say** (`repositories/hys.py`): the consultation is joined to the law by COM
  reference only. `crawl_index` over about 4,128 initiatives (resumable through the
  cache, about 35 minutes uncached), `find_initiatives(index, com_reference)` exact
  match, `find_by_title` as a labelled fallback; `iter_feedback(fetcher, publication_id)`
  paging to `last`, raising `HysUnavailable` when the questionnaire is not served;
  `feedback_records` and `fetch_attachment` to `SourceDocument` and `DocumentText`, a
  failed PDF counted, not dropped.
- **Passages** (`services/passages.py`): one to three sentences, overlapping by one, with
  half-open code-point offsets such that `text[start:end]` is the passage, always.
- **Register and actors** (`repositories/register.py`, `services/actors.py`): never merge
  two register IDs; never merge on an acronym alone; never merge an association with its
  members; a register ID absent from today's export keeps its identity; an exact name
  matching several entries is `ambiguous` with `candidate_ids`; fuzzy and acronym matches
  are proposals with a score, not merges.

## Data on Disk

Under the git-ignored `data/` of this checkout, downloaded 3 October about 12:20 CEST:
`data/raw/parltrack/{ep_dossiers,ep_meps,ep_plenary_amendments,ep_amendments}.json.zst`
(55.3 MB, 9.4 MB, 7.0 MB, 120.0 MB) and `data/raw/registry/register.xml` (the daily
Transparency Register export). `data/cache/` holds whatever the sub-agents fetched. A
new machine re-downloads the dumps from `https://parltrack.org/dumps/<name>.json.zst`
and the register from
`https://ec.europa.eu/transparencyregister/public/files/ODP/download/XML/latest`; a
scripted download command is part of step 3 and does not exist yet.

## This Laptop

Windows 11, Intel Core Ultra 7 258V, 32 GB. An Application Control policy blocks
`uv.exe`, so Python runs in WSL Ubuntu: uv 0.12.8 in `~/.local/bin`, the environment in
`~/venvs/influence`. `make` is not installed (no passwordless `sudo` in WSL), so run the
Makefile targets' commands directly, inside WSL:

```sh
export PATH="$HOME/.local/bin:/usr/bin:/bin" UV_PROJECT_ENVIRONMENT="$HOME/venvs/influence" UV_EXCLUDE_NEWER="14 days"
cd /mnt/c/Proyectos/Reversa/reversa-madrid-open/backend
uv sync --locked
uv run --locked ruff format --check src tests && uv run --locked ruff check src tests
uv run --locked basedpyright
uv run --locked pytest --cov
```

Frontend gates were not run in this session; no frontend file changed. `gh` is logged in
as `EstrellaTP`. `tbd` 0.9.0 is installed through npm and takes one to two minutes per
command here.

## Beads

Not confirmed. A command that creates the contracts bead, the CLI/API and UI child beads
of `rev-qn6b`, and claims `rev-pjk2` (taken over from the cloud session with the owner's
agreement) was started at about 12:45 and had printed nothing by 14:15. Run `tbd list`
before creating anything, to avoid duplicates. Still owed: record PR #25 and #26 on
`rev-pjk2`, write the two child bead IDs into this folder's Agent 1 and Agent 3 files,
create a bead per remaining step above, and `tbd sync`.

## Open Questions for the Owner

- Merge PR #25, so Agents 2 and 3 build on `main`.
- Insertions with no `old` text: unknown (`null`) or known empty (`""`)?
- Should `feat/extraction-foundations` get its own PR, or be reviewed inside #26?
