# The Influence Atlas: Technical Plan

Reversa x Madrid Open, Challenge 03.

## 1. Goal

Build an open, public map of who shapes EU law: **actor -> ask -> amendment -> final article**, for any EU law since 2019, with every edge backed by visible evidence.

Judged live (100 points): Real links 25 | Any law 20 | Insight 25 | Report 15 | Ambition 15.

Deliverables: an explorable graph, a short public report answering the five questions (Who, What, Towards what, How, Next), and an open-source repo anyone can rerun.

## 2. Design principles

1. **Evidence first.** Every edge is a verifiable claim: the ask, the amendment and the final article, side by side.
2. **Precision over recall.** The jury reads three random edges live. Show only high-confidence edges by default.
3. **Law-agnostic.** No per-law code or tuning. Scores are relative to each law's own background distribution.
4. **Cheap before expensive.** Lexical and embedding filters first; the LLM only sees surviving candidates.
5. **Graceful degradation.** If a data channel is missing for a law, fall back to the next one and label it. Never show an empty screen.
6. **Careful wording.** Write "the ask appears in the amendment", never "X wrote the law". Echo is not causation.

## 3. Data sources (status checked 3 Oct 2026)

| Source | Access | Status |
|---|---|---|
| Parltrack | JSON dumps, zstd-compressed, base URL `https://parltrack.org/dumps/`: `ep_dossiers`, `ep_amendments`, `ep_plenary_amendments`, `ep_meps`, `ep_votes`, `ep_com_votes`. ODbL v1.0 | Verified. **Committee amendments dump last updated 2026-02-03**; plenary amendments and dossiers 2026-07-24 |
| EP Open Data API v2 | `https://data.europarl.europa.eu/api/v2`: `/procedures`, `/procedures/{id}/events`, `/committee-documents`, `/documents`, `/meetings`. JSON-LD, no auth, limit 500 requests per 5 minutes, `offset`/`limit` pagination | Verified |
| EUR-Lex | Python library `eurlxp`: HTML by CELEX (`https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:...`) or SPARQL at `https://publications.europa.eu/webapi/rdf/sparql` (recommended, avoids bot detection). Returns a DataFrame with article and paragraph columns | Verified |
| HowTheyVote | CSV.gz files in GitHub releases of `HowTheyVote/data`, weekly updates, plenary roll-call votes only | Verified |
| EU Transparency Register and Commission meetings | Per Integrity Watch, available as datasets on the EU Open Data Portal ("EU Lobbyists", "Commission meetings") | Partial: dataset pages not inspected |
| MEP meetings | Scraped from individual MEP pages on europarl.europa.eu (as Integrity Watch does) | Not verified |
| Have Your Say (HYS) | PyPI package `hys-scraper` (`pip install hys_scraper`, then `python3 -m hys_scraper <publication id>`); writes `feedbacks.csv`, `attachments.csv`, `countries.csv`, `categories.csv` and an `attachments/` folder. Archived March 2026, last release September 2023, so it may not match the current portal | **Exists, not yet tested against the current portal. Highest-risk connector.** Try it first (time-box 10 minutes). If it fails, discover the portal's own JSON endpoints by inspecting browser network requests (time-box 30 minutes) |

### Parltrack fields we rely on

- `ep_amendments`: `id`, `old` (list), `new` (list), `justification`, `authors`, `meps` (MEP ids), `reference` (procedure ref, e.g. `2023/0397(COD)`), `committee`, `location`, `date`, `compromise`, `src`.
- `ep_dossiers`: `procedure.reference`, `procedure.title`, `procedure.subject`, `procedure.stage_reached`, `committees[]` (with `rapporteur`, `shadows`), `events[]` (with `docs`), `final` (final act with EUR-Lex URL, present only in a subset), `links`.

### Obligations

Parltrack and Integrity Watch data are ODbL v1.0. Attribute them in the README and the report, and check the share-alike terms for any derived dataset we publish.

## 3b. The law bundle: what we fetch for one law

When someone names a law, we do **not** download "everything". We build a **bundle** of six folders for that law's legislative procedure. Each folder is requested with a key taken from the `LawRecord` (stage [0]) or from documents already fetched.

| # | Folder | Contents | Source | Key | Required? |
|---|---|---|---|---|---|
| 1 | **Law texts** | Commission proposal (base text) and final act (outcome). Optional: Parliament's first-reading position | EUR-Lex via `eurlxp` | CELEX codes | Yes |
| 2 | **Amendments** | Each amendment: old text, new text, justification, authors (MEP ids), committee, date, compromise links | Parltrack `ep_amendments` and `ep_plenary_amendments`; EP API if the dump is stale | Procedure reference (`reference` field) | Yes |
| 3 | **Lobby asks (submissions)** | Each HYS feedback item: organisation, type, country, Register id, date, text, attached PDFs. Tag each with its HYS `phase` | Have Your Say (`hys_scraper` or own client) | HYS initiative id(s) | Yes. It is the origin of the edges |
| 4 | **Who is who** | Organisations (category, declared spend, staff); MEPs (name, group); procedure roles (rapporteur, shadows) | Transparency Register dataset, `ep_meps`, `ep_dossiers` | Ids found in folders 2 and 3 | Yes (needed for ranking and the insight) |
| 5 | **Context signals** | Commission and MEP meetings; plenary and committee votes | Meetings datasets, HowTheyVote, `ep_com_votes` | Dates and subject / dossier | No. It is the fallback channel and feeds the channel analysis |
| 6 | **Metadata** | Title, subject, key dates (proposal, committee vote, plenary, publication), stage reached | `ep_dossiers` | Procedure reference | Yes (small) |

### Join keys

- `procedure_ref` joins amendments to the dossier.
- MEP id joins amendments to the MEP table and to dossier roles.
- Transparency Register id joins submissions to the Register (fuzzy name match when the id is missing).
- CELEX joins the proposal to the final act.

### Fetch order

1. Stage [0] produces the `LawRecord`.
2. In parallel: law texts (CELEX), amendments (procedure ref), submissions (HYS initiative id).
3. Then actors and MEPs, **only for the ids that appear** in the amendments and submissions (fetch by key; do not load whole registers into the pipeline).
4. Optional context (meetings, votes) last.

### Rules

- **Stream and filter big dumps.** The Parltrack dumps cover every procedure. Read them as a stream and keep only rows whose `reference` matches. Never hold a full dump in memory.
- **Submission phases.** A law can have several HYS phases (earlier consultations, feedback on the proposal). Include all phases linked to the law, tagged with `phase`. The delta against the Commission's base text already removes asks the Commission adopted, and the chronology rule keeps only submissions dated before the amendment. Optional extension, if time allows: matching submissions to the Commission proposal itself (pre-proposal influence).
- **One name, several procedures.** A name such as "AI Act" can map to the original law and to later proposals that amend it. The resolver shows the candidates and the one chosen; `--procedure <ref>` overrides it.
- **Not fetched:** other laws (except precomputed bundles used to train the forecast), Council documents, press, social media, non-EU sources.
- **Size varies a lot.** Large laws can have hundreds of submissions and thousands of amendments; small ones a few dozen. Do not assume numbers: log the real counts in `coverage` on every run.

### `coverage` schema (stored in the `LawRecord`)

```
coverage:
  texts:        {proposal: true, final_act: true}
  amendments:   {count: N, source: parltrack|ep_api, last_updated: YYYY-MM-DD}
  submissions:  {count: N, phases: [...], with_attachments: N}
  actors:       {matched_to_register: N, unmatched: N}
  context:      {commission_meetings: N, mep_meetings: N, votes: true|false}
```

### Degradation modes (always label them in the UI)

| What is missing | Mode | UI label |
|---|---|---|
| Submissions | Contextual evidence: amendment authors, Register, meetings, votes | "Contextual evidence, not textual" |
| Amendments (but submissions and final text exist) | Match submissions directly to the final text | "No amendment stage" |
| Final act (law still being negotiated) | No survival step; forecast mode only | "Negotiation in progress" |
| Fresh amendments missing from the dump (stale) | EP API plus PDF parsing for the new documents | "Partial amendment coverage" |

## 3c. Setup (once, before the hackathon work) vs runtime (per law, live)

The system does NOT only work for laws we mapped by hand. Only a **catalog** is prepared in advance; the `LawRecord` is built live for whatever law is named.

| | When | What | Cost |
|---|---|---|---|
| **Setup (one time)** | First step, then never again | Download `ep_dossiers` (~53 MB, covers every legislative procedure) and load it into DuckDB `dossiers`. Optionally download `ep_meps`, `ep_amendments`, `ep_plenary_amendments`, `ep_com_votes` the same way. Write the seed alias list (~50 popular laws, `data/aliases.yaml`). | Minutes |
| **Runtime (per law)** | Every `atlas run --law X` | Resolver searches the catalog and **builds the `LawRecord` on demand** (seconds), caches it in `cache/laws/{procedure}.json`; then connectors fetch the law bundle (3b) and stages [1]-[10] run. | Seconds for the record, minutes for the rest |
| **Precompute (safety net)** | After the any-law CLI works | Run 10-15 laws end to end into `demo/` so the live demo survives a network failure. This is a speed backup, not a limit on which laws work. | Background job |

Rules:
- The alias list only improves free-text matching ("AI Act" -> its procedure). A law missing from it still resolves by fuzzy title, procedure reference, CELEX or COM number.
- **Newer than the dump:** `ep_dossiers` was last updated 2026-07-24. If the resolver finds no match, or the matched dossier lacks a proposal or final act, fall back to the EP API (`/procedures`, `/procedures/{id}/events`), build the `LawRecord` from it, and set `warnings: ["not in Parltrack dump"]`.
- A `LawRecord` is cached; rerunning the same law reuses it. `--refresh` forces a rebuild.
- Never fail with an empty screen: if resolution is uncertain, show the top 3 candidate laws and let the user pick, or run the best guess with `confidence: low` clearly labelled.

## 4. Architecture

```
 Law name
    |
 [0] RESOLVER --> LawRecord {procedure, COM, final act, HYS initiative, coverage}
    |
 [1] CONNECTORS (one per source, same interface, disk cache by URL)
    |   HYS | Parltrack / EP API | EUR-Lex | Register | Meetings | Votes
 [2] NORMALISE --> documents -> clauses (article/recital) -> chunks (<=350 tokens)
    |
 [3] DELTA --> diff(base, amendment) = inserted / deleted text
    |
 [4] CANDIDATES (cheap, no LLM): BM25 + embeddings, scores vs the law's background,
    |    local alignment on rare n-gram anchors
 [5] VERIFIER (LLM, top-k only): atomic asks, JSON with verbatim evidence
    |
 [6] EDGES (tiers A/B/C) --> [7] SURVIVAL (amendment -> final act)
    |
 [8] GRAPH + METRICS (shrunk success rate, shared credit, success vs spend)
    |
 [9] FORECAST --> [10] OUTPUTS: graph.json | static web app | report.md
```

Stages are idempotent and cached. A tiny runner (`@stage(name, deps)`) stores each output as Parquet and skips work whose inputs have not changed. `atlas run --law X --from <stage>` reruns from any point.

## 5. Stages

### [0] Resolver
- Setup (once, see 3c): load `ep_dossiers` into a DuckDB table `dossiers(reference, title, subject, stage, final_url, committees, events)`. At runtime, query that table and build the `LawRecord` on demand; cache it. If no match or the dossier is newer than the dump, fall back to the EP API `/procedures`.
- Detect input type: procedure `\d{4}/\d{4}\([A-Z]+\)`, CELEX, `COM\(\d{4}\)\s?\d+`, or free text.
- Free text: `rapidfuzz.token_set_ratio` on normalised titles plus a seed alias list of about 50 popular laws (AI Act, DSA, DMA, Data Act, CSRD, CSDDD, Cyber Resilience Act, ...) verified once by hand. If the top two candidates are close, an LLM disambiguates. Always show which law was chosen.
- Proposal COM: regex over `events[].docs`. Proposal CELEX: `5{year}PC{number:04d}`, for example `52021PC0206` (verify on the first law). Final act CELEX: parse from `final.url`.
- HYS initiative: fuzzy title match plus a date window around the proposal date.
- Fill `coverage` by probing what exists (number of submissions, amendment records, final text). Set `confidence` and `warnings`.

### [1] Connectors
- Common interface `fetch(law_record) -> RawDoc[]` with `source`, `url`, `retrieved_at`, `content_type`, local path, metadata.
- `httpx` async, `tenacity` retries, per-host rate limit, disk cache keyed by sha256(url), identifiable User-Agent.
- Parltrack streaming reader (verify the line prefixes `[`, `,`, `]` on the first file):

```python
import zstandard, json, io
def stream(path):
    with open(path, "rb") as f, zstandard.ZstdDecompressor().stream_reader(f) as r:
        for line in io.TextIOWrapper(r, encoding="utf-8"):
            line = line.strip()
            if line in ("[", "]", ""): continue
            yield json.loads(line.lstrip(",").lstrip("["))
```

- EP API: at most about 1 request per second to stay under the limit. Use it for fresh committee documents when the Parltrack dump is stale.
- EUR-Lex: async `eurlxp` client with a 2-second delay.
- HYS: wrap `hys_scraper` first (`HYS_Scraper("<publication id>").scrape()` returns feedbacks, countries and categories, and downloads attachments). Its publication id is the `p_id` parameter of the old portal URL, which may differ on the current portal. Treat its output as untrusted until checked on one initiative: row counts match the portal, attachments open, dates parse. Use its code as a reference if we have to write our own client.

### [2] Normalise
- Clauses: take article and paragraph columns from the `eurlxp` DataFrame; build ids like `art5.1.a`, `rec23`.
- Amendments from Parltrack need no PDF parsing. For fresh amendments only available as PDF, use `pdfplumber` table extraction (two columns: Commission text, amendment).
- Submissions (PDF): `pymupdf` blocks, remove repeated header/footer lines, de-hyphenate, split sentences with `pysbd`, build chunks up to 350 tokens with one sentence of overlap and character offsets.
- Language detection; keep non-English documents but flag them (multilingual embeddings and the LLM still work, lexical features degrade).
- Campaign detection: `datasketch` MinHash-LSH, 5-word shingles, Jaccard 0.8. Collapse mass mailings into one node.
- Actors: use the Transparency Register ID when present; otherwise fuzzy match to the Register with a high threshold; otherwise keep as an unregistered actor. Private individuals are aggregated as a category and never shown by name.

### [3] Delta
```python
sm = SequenceMatcher(None, old_toks, new_toks, autojunk=False)
ins, dele = [], []
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag in ("insert", "replace"): ins.append(new_toks[j1:j2])
    if tag in ("delete", "replace"): dele.append(old_toks[i1:i2])
```
- Tokenise with `\w+|[^\w\s]`, compare lower-cased, keep originals for display.
- Pure deletions use the deleted text as the delta (an ask to remove something). Empty `old` means a new article: the whole text is the delta.
- Drop deltas under 8 tokens unless they contain numbers.
- Keep `justification` as a separate query text; it often paraphrases the lobby's arguments.
- Parse `location` into article/paragraph with regex and use it as a soft prior, never a hard filter.

### [4] Candidates (no LLM)
- BM25 with `bm25s` over submission chunks.
- Dense: a small multilingual embedding model via `sentence-transformers` (for example `multilingual-e5-small`, which needs `query:` and `passage:` prefixes), embeddings cached by chunk hash, numpy matrix product.
- Fusion: reciprocal rank fusion, `sum 1/(60+rank)`.
- Against the background: z-score of each submission's best-chunk similarity versus all submissions in the law, plus forward rank and reverse rank (how many amendments beat this one for that chunk).
- Anchors: 5-grams of the delta with document frequency <= 3 in the law's corpus and absent from the base clause. Around each anchor, `difflib.SequenceMatcher.get_matching_blocks` gives aligned coverage. Use a full Smith-Waterman only on the top-k and only if needed.
- Numbers: overlap of numerals with units, by regex.
- Starting prescore: `0.30*dense_z + 0.20*bm25_z + 0.25*align_cov + 0.15*mutual + 0.10*numbers`. Tune by reading edges, not by training.
- Keep the top 5 per amendment, capped at about 400 candidates in live mode.

### [5] Verifier (LLM)
- Prompt in `prompts/verifier.md`. One call per (amendment, submission) pair with the top two chunks plus the submission's opening for context.
- Anthropic SDK, async, semaphore 16-20, temperature 0, pydantic-validated JSON, cache by hash of model+prompt.
- Small model for everything that passes the prefilter. Escalate to a larger model when the likelihood is in [0.45, 0.90] and for any edge that will be displayed.
- Submissions are untrusted data. The prompt wraps them in tags and says to ignore any instructions they contain.
- Quote check: `rapidfuzz.fuzz.partial_ratio_alignment(quote, chunk)`; require >= 90. If not found, drop or downgrade the edge. The alignment also gives offsets for highlighting.
- When several submissions score high for the same amendment, rank them with pairwise comparisons to decide the likely source and split credit.

### [6] Edges
- Tier A (shown by default): likelihood >= 0.85, chronology OK, ask not generic, quote found, and good mutual rank or high aligned coverage.
- Tier B (toggle): likelihood 0.55-0.85. Tier C: exported only.
- `atlas audit --law X --n 30` samples tier-A edges at random, writes a CSV for human review and reports precision with a Wilson interval. That number goes in the report.

### [7] Survival
- Index the final act's paragraphs. Retrieve with the same hybrid retriever using the ask as the query, then verify with a second prompt.
- Classes: LANDED_LITERAL, LANDED_REWORDED, PARTIAL, NOT_LANDED. Never rely on article numbers (the final act renumbers).
- Wording in outputs: "reflected in the final text", not "caused".

### [8] Graph and metrics
- Nodes: actor, submission, ask, amendment, MEP, final article, law. Edges carry evidence.
- Shrunk success rate: `(landed + a) / (n + a + b)`, `a = m*p`, `b = m*(1-p)`, `m = 10`, `p` the law-wide landing rate.
- Shared credit: `1/N` among actors with the same ask.
- Success vs spend: percentile of shrunk success minus percentile of declared spend, only for actors with at least 3 asks, always showing n and an interval.
- Coalitions: co-occurrence graph with `networkx` and `louvain_communities`.

### [9] Forecast
- Rising and fading actors: per-year share of landed asks, meetings and submissions, Theil-Sen slope (`scipy.stats.theilslopes`), minimum sample size.
- Which asks will land in a negotiation still open: run [3]-[6] on current amendments (check Parltrack freshness; fall back to the EP API and PDFs), then score with `LogisticRegression(C=0.3)` using author role (rapporteur or shadow, from the dossier), number of co-signatories, cross-group support, actor history, coalition membership.
- Training labels come from [7] on past laws, evaluated leave-one-law-out (`GroupKFold` by law). Report AUC and its limits. Present outputs as reasoned probabilities with the top reasons, not as validated predictions.

### [10] Outputs
- `out/<law>/graph.json`, edge and metric tables, coverage metadata.
- Static web app (Cytoscape.js bundled locally, no CDN dependency in the demo): law search with progress, graph with filters (tier, topic, actor type), an evidence panel with four columns (Commission text, amendment with delta highlighted, submission with quote highlighted, final article) plus the reason and source links, success-vs-spend view, forecast view.
- FastAPI: `POST /run`, SSE for progress, `GET /graph/{law}`.
- `report.md` via Jinja2 with numbers from `metrics.json`. The LLM drafts narrative using only those numbers; a human edits. Includes methodology, limits, audited precision and a coverage table.

## 6. Data model (DuckDB)

`laws`, `raw_docs`, `documents`, `clauses`, `chunks`, `submissions`, `amendments`, `asks`, `candidates`, `verifications`, `edges`, `survival`, `actors`, `metrics`. Every row carries `source_url` and `retrieved_at`.

## 7. Repo layout

```
atlas/
  sources/   resolver.py parltrack.py ep_api.py eurlex.py hys.py register.py meetings.py votes.py
  ingest/    normalize.py clauses.py campaigns.py actors.py
  nlp/       delta.py retrieve.py align.py verify.py survival.py
  graph/     edges.py metrics.py forecast.py
  app/       cli.py api.py
web/         index.html app.js
prompts/     verifier.md
tests/       fixtures/<one-law>/
demo/        precomputed outputs for several laws
config.yaml  PLAN.md  PROGRESS.md  README.md  LICENSE  .env.example
```

## 8. Config defaults (`config.yaml`)

```
chunk_max_tokens: 350
chunk_overlap_sentences: 1
delta_min_tokens: 8
retrieval_k: 50
rrf_k: 60
topk_per_amendment: 5
live_candidate_cap: 400
prescore_weights: {dense: 0.30, bm25: 0.20, align_cov: 0.25, mutual: 0.15, numbers: 0.10}
verifier: {escalate_range: [0.45, 0.90], temperature: 0, concurrency: 16}
tiers: {A: 0.85, B: 0.55}
quote_match_min: 90
shrinkage_m: 10
min_asks_for_ranking: 3
```

Model names come from environment variables (`VERIFIER_SMALL_MODEL`, `VERIFIER_LARGE_MODEL`); the API key from `ANTHROPIC_API_KEY`. Never hardcode either.

## 9. Risks and mitigations

1. **Linking initiative, procedure and final text** is the most fragile step. Validate the resolver on three laws before building further; `confidence` and `coverage` guard against silent mismatches.
2. **HYS access.** Test `hys_scraper` first (10 minutes). If it fails, discover the portal's endpoints (30 minutes). If that fails too, run in contextual-evidence mode (amendments, authors, Register, meetings, votes) and label it.
3. **Stale amendment dump.** Check `ep_amendments` freshness per law; fall back to the EP API and PDF parsing.
4. **Bad PDF extraction.** Measure usable-text ratio per document and drop poor ones rather than risk bad edges.
5. **LLM latency and cost live.** Cheap prefilter, aggressive cache, candidate cap, precomputed fallback.
6. **Over-claiming.** Use the careful wording rules; publish the audited precision.

## 10. Out of scope

Fine-tuning, heavy local models, US/other-country expansion, social media ingestion, and any complex front end. Revisit only if everything above is done.

## 11. Verification checklist (before building on any source)

- [ ] `ep_dossiers` loads; the first line format matches the reader.
- [ ] Resolver returns correct records for three known laws.
- [ ] For each: amendments exist in Parltrack, with `old` and `new` populated.
- [ ] CELEX construction yields a proposal that `eurlxp` can fetch.
- [ ] `hys_scraper` tested on one initiative (the publication id comes from the portal URL); otherwise endpoints found, or fallback mode decided.
- [ ] Register and Commission meetings datasets located on the EU Open Data Portal.
- [ ] For the pilot law, real counts logged in `coverage` (amendments, submissions with attachments, matched actors).
- [ ] Pilot law chosen and written in PROGRESS.md.
