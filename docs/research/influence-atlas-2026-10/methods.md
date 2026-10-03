# Research: Methods for The Influence Atlas, Built in One Day

Saturday 3 October 2026, Madrid Open, Reversa Challenge 03. Written for a team of 3–4
building on a MacBook (Apple Silicon) with Python 3.14, with demos at 19:30 CEST.

**Status tags**

- `verified`: I read the primary source (paper, model card or official page) today.
- `reported`: from search-result summaries or other secondhand sources. Check before you
  quote it to the jury.
- `measured`: I ran it today on this machine, an Apple M5 with 24 GB RAM, using
  Python 3.14 through `uv`. Scripts are in the scratchpad (`bench.py`, `embbench.py`).
- `estimate`: arithmetic from the stated assumptions; nothing was run.

The existing catalogs (`docs/research/influence-2026-10/tools.yaml` and
`existing-systems.yaml`) already cover LobbyPlag, LID, Copy-Paste-Legislate, Wilkerson,
Suresh et al., the model licences and the Claude prices. This report builds on them and
does not repeat their entries. Section headings use the part names from the
`influence-architecture` skill (3 Find candidates, 4 Verify links, 5 Trace outcomes,
7 Analyse).

---

## The Pipeline on One Screen

| Part | One-day recommendation | Fallback |
| --- | --- | --- |
| 2 Resolve actors | Transparency Register ID first; then normalised name with exact match; then RapidFuzz ≥ 92 within the same country and type; check the top actors by hand | Exact normalised name only |
| 3 Find candidates | Per law, in memory: BM25 (`bm25s`) on the change's rare tokens, plus dense cosine (BGE-M3 or Qwen3-Embedding-0.6B) between change and passage. Brute-force numpy, top 20 from each, merged with reciprocal rank fusion. No vector database | BM25 only; or the cached `paraphrase-multilingual-mpnet-base-v2` |
| 4 Verify links | Mask boilerplate first (text quoted from the proposal, phrases common across the corpus). Then cheap signals, then a structured LLM judge on the top 1–3 candidates per amendment. The judge gives a relation label, direction and evidence spans; code checks each span with an exact substring match. A logistic combiner calibrated on LobbyPlag. Publish only above a strict threshold | Cheap signals and the combiner only; the NLI model vetoes contradictions |
| 5 Trace outcomes | Align articles between Commission proposal, EP position and final act. An ask or amendment "won" if its inserted rare tokens or aligned span appear in the final article and were absent from the proposal. Add a Laloux & Delreux word-origin split at institution level | Check only whether the change appears in the EP position |
| 7 Analyse: rank | Wins counted per actor as "changed the text" separately from "defended the status quo"; win rate with beta-binomial shrinkage | Raw counts with n shown |
| 7 Analyse: explain | 5–10 hand-picked actors: LLM extracts claims with quoted spans from public statements and from asks; stance compared per provision on InfluenceMap's −2..+2 scale; every flag reviewed by a person | Show the two quotes side by side with no automatic stance |
| 7 Analyse: forecast | Logistic regression on ask features (coalition breadth, counter-coalition, rapporteur or draft-report inclusion, status-quo direction, actor type). Split by procedure completion date | The "rapporteur's draft includes it" rule as baseline |
| Topics | OEIL subject codes and the EUR-Lex EuroVoc descriptors already attached to the procedure; submissions inherit them | Zero-shot LLM over about 20 top-level subjects |
| Languages | Compare each submission with the official translation of the amendment or proposal in the submission's own language, using lexical signals; dense retrieval is cross-lingual; machine translation is for display only | OPUS-MT for display |

**Why precision matters above all** (`estimate`). The jury samples 3 links. If the share
of real links is p, then all three pass with probability p³. That is 0.73 at p = 0.90,
0.86 at 0.95 and 0.94 at 0.98. Publish fewer, stricter links. Mark everything else
"unconfirmed" and keep it out of the published graph that the jury samples from.

---

## 1. Finding Candidates at Scale (Part 3)

### Recommended

**Units.**

- *Query*: one amendment change, meaning its inserted and deleted words, with one sentence
  of context on each side.
- *Document*: one submission passage, a window of 1–3 sentences (about 40–120 words)
  overlapping its neighbours.

Index by procedure (one law), never the whole corpus. The scale is set by the law: about
1–3k amendments × a few hundred submissions × a few dozen passages each, so about 10–60k
passages.

**Two retrievers, unioned.**

1. **BM25** over passages, with `bm25s` (MIT; NumPy and SciPy only).
   - The authors report speed-ups of up to 500× over the most popular Python
     implementation (`reported`, arXiv 2407.03618).
   - The query is the change's tokens. Weight them with corpus IDF and drop the
     boilerplate n-grams from section 2.
   - BM25 catches verbatim and near-verbatim reuse cheaply.
2. **Dense cosine** between the change and each passage, with a multilingual encoder.
   - Normalise the vectors and take `q @ X.T` with NumPy.
   - It catches paraphrase and other languages.

Take the top 20 from each retriever and merge them with **reciprocal rank fusion**:
each candidate scores Σ 1/(60 + rank). Keep about 20–30 candidates per amendment.

Optional boost: a regex for article references in a passage ("Article 5(2)", "Art. 5"),
pointing at the article the amendment changes. Lobby papers usually name the article.

**Measured: an in-memory index per law is more than enough** (`measured`, Apple M5,
NumPy, float32, 1024 dimensions, exact top-20):

| Queries × passages | Time | Index RAM |
| --- | --- | --- |
| 2,000 × 9,000 | 0.14 s | 37 MB |
| 2,000 × 60,000 | 0.90 s | 246 MB |
| 20,000 × 200,000 | 30 s | 819 MB |

FAISS, hnswlib and usearch are therefore unnecessary per law. Consider one only for an
index across the whole corpus (more than 1M vectors).

**Measured: encoding speed** (`measured`).

- `paraphrase-multilingual-mpnet-base-v2` encoded **225 texts/s** on M5 with the MPS
  backend (torch 2.14.1, sentence-transformers, batch 64, about 67 tokens per text).
  That model has about 278M parameters and is already cached locally.
- BGE-M3 and multilingual-e5-large are XLM-R-large models of about 560M parameters.
  Expect them to be several times slower (`estimate`, not measured).
- So one law (about 15k texts) takes roughly 1 minute with mpnet and a few minutes with
  BGE-M3 (`estimate`).
- All 540k amendments would take about 40 minutes even with mpnet (`estimate`).
- Conclusion: embed per law on demand and cache the vectors (`data/emb-cache` exists).
  Pre-warm the laws you expect the jury to name.

**Choosing the encoder takes 30 minutes.** Measure recall@20 on LobbyPlag's 172 verified
pairs: for each verified amendment, is its verified proposal among the top 20 of all
proposals for the same law? Run it for BM25 alone, for each dense encoder alone and for
the fused list, then pick the best. No encoder has been measured on our data yet, so do
not choose one by its benchmark scores.

### Models

| Model | Licence | Size | Context / dim | Notes | Status |
| --- | --- | --- | --- | --- | --- |
| BGE-M3 (BAAI) | MIT | ~568M | 8192 / 1024 | One pass gives dense, sparse (lexical weights) and ColBERT multi-vector outputs. Its sparse output can replace BM25 for other languages | `verified` (model card); size `reported` |
| Qwen3-Embedding-0.6B | Apache-2.0 | 0.6B, 28 layers | 32k / up to 1024 (Matryoshka) | MMTEB multilingual 64.33. Instruction-aware; the card says instructions add 1–5%. Needs sentence-transformers ≥ 2.7 | `verified` (model card) |
| multilingual-e5-large-instruct | MIT | ~560M | 512 / 1024 | XLM-R-large; solid cross-lingual retrieval | `reported` |
| EmbeddingGemma-300M | Gemma licence; Hugging Face requires accepting Google's terms | 300M | 2048 / 768 (Matryoshka down to 128) | Small and fast, but a custom licence and a sign-in gate on the day | `reported` |
| jina-embeddings-v3 | CC BY-NC 4.0 | ~570M | 8192 | **Reject**: non-commercial, so Reversa could not reuse it | `reported` |
| paraphrase-multilingual-mpnet-base-v2 | Apache-2.0 | ~278M | 128 / 768 | Already cached; 225 texts/s measured; older and weaker | `measured` |

Runtimes:

- **sentence-transformers on MPS** is the least-risk path, and it worked today.
- **MLX** ports exist for some embedders. One model card reports MLX about 1.8× faster
  than PyTorch/MPS, for a different model on M1 Pro (`reported`). Do not switch runtimes
  today unless encoding time measurably blocks you.

### Fallbacks

1. BM25 only, plus the existing rarity-weighted Smith-Waterman. This finds verbatim reuse
   and misses paraphrase.
2. The cached mpnet model for the dense half.

### Rejected

- **Whole-document embeddings.** Already measured: decoys score higher than real copies
  (catalog entry `whole-text-embeddings`).
- **Vector databases** (Qdrant, Milvus, pgvector). They add operations work and give no
  gain at 10⁴–10⁵ vectors.
- **Elasticsearch, as LID used.** A JVM service to run; `bm25s` runs in-process.
- **A corpus-wide index today.** Not needed for "name any law".

---

## 2. Verifying Influence Against Boilerplate and Paraphrase (Part 4)

### Recommended: a three-stage cascade

**Stage A: mask boilerplate before any scoring.**

1. **Quoted law.** Remove every token span of 8 or more words that appears verbatim in
   the Commission proposal, or in the act being amended. The diff (inserted and deleted
   words) does most of this already; also apply it to the submission passage, because
   lobby papers quote the proposal.
2. **Standard wording across the corpus.** Over all amendments (Parltrack) and all
   submissions, compute the document frequency of each word 3-, 4- and 5-gram, counting
   distinct authors.
   - Mask or down-weight n-grams found in more than about 0.5% of documents, or used by
     more than about 20 distinct authors. Typical examples: "without prejudice to",
     "Member States shall ensure that", "in accordance with Article".
   - Tune both cut-offs on LobbyPlag decoys.
   - This is the IDF idea applied to phrases. It also explains in a sentence why a link is
     "not shared standard wording".
3. **Template campaigns.** The same paragraph in many submissions from *different*
   organisations on the same law is coordinated campaign text, not standard wording. Do
   not discard it. Attribute the link to the cluster, give it a "coalition" flag and list
   its members.

**Stage B: cheap signals**, as already designed: IDF-weighted rare shared n-grams,
Smith-Waterman local alignment, character similarity, same edit in the same direction,
the shall/may/not polarity check, and dense cosine of the two changes.

**Stage C: an LLM judge on the top 1–3 candidates per amendment** that pass a cheap gate.

- **Prompt input**: only the extracted change (deleted → inserted, with context), the
  candidate passage and the article reference. Never whole documents.
- **Structured output** fields:
  - `relation` ∈ {`verbatim_reuse`, `paraphrased_reuse`, `same_goal_different_wording`,
    `opposite_request`, `topic_only`}
  - `direction_match` (bool)
  - `standard_wording` (bool)
  - `amendment_evidence` and `submission_evidence`: lists of exact quotes
  - `confidence` (0–1)
- **Hallucination guard**: code keeps an evidence span only if it is an exact substring
  (after whitespace normalisation) of its source. If no span survives, the label falls to
  `topic_only`. The surviving spans also feed the side-by-side view the jury reads.
- **Use the judge as features, not as the score.** Its relation label and confidence go
  into the logistic combiner. Calibrate the combiner on LobbyPlag pairs plus synthetic
  paraphrase and contradiction decoys.

**Contradictions** (the reranker failure you measured).

- Rerankers and embeddings reward topic. Use them only to order candidates.
- Three checks can veto acceptance:
  - the polarity check;
  - multilingual NLI (`mDeBERTa-v3-base` XNLI, MIT, already in the catalog) on change
    against requested change, where contradiction above a threshold vetoes;
  - the judge's `opposite_request` label.

**Prior evidence for an LLM in this role.** Casas & Rodilla Lázaro (ECPR General
Conference 2025) use LLMs for text reuse to measure amendment success.

- Corpus: about 93,000 Spanish amendments, 1996–2019.
- Validation: a hand-coded set of more than 5,000 amendments.
- They name *deletion-only* amendments as a case classic text reuse misses (`verified`,
  abstract only; no accuracy numbers given).

### Cost of an LLM judge (`estimate`)

Prices are `reported` from the claude-api skill reference, cached 25 September 2026.

Assumptions:

- About 1,200 input tokens per pair: a 400-token instruction that can be cached, a
  300-token change and a 500-token passage.
- About 150 output tokens of JSON.
- Thinking off or minimal.

| Model | Price per MTok (in / out) | 10k pairs, standard | 10k pairs, Batch API (−50%) |
| --- | --- | --- | --- |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | $2 / $10 | ≈ $24 + $15 = **$39** | ≈ **$20** |
| Claude Haiku 4.5 (`claude-haiku-4-5`) | $1 / $5 | ≈ $12 + $7.5 = **$20** | ≈ **$10** |
| Claude Opus 5.5 (`claude-opus-5-5`) | $4 / $20 | ≈ **$78** | ≈ **$39** |

Caveats:

- **Thinking on Sonnet 5.5** is adaptive and on by default, so it adds output tokens. To
  turn it off, send `thinking: {type: "between_tools"}`, which is accepted only at effort
  `high` or below. Or keep thinking on at effort `low`.
- **Caching**: the cached instruction prefix is billed at the cache-read rate, $0.20/MTok
  on Sonnet 5.5.
- **Batch is asynchronous.** It suits precomputing popular laws, not the live "name any
  law" demo, which needs the regular API with bounded concurrency.

**Local judge.** Qwen3-4B-Instruct through `mlx-lm` (Apache-2.0 and MIT) works offline and
gives token probabilities as a score. I did not measure its speed today; at about 1.3k
prompt tokens per pair, reading the prompt dominates. Measure tokens/s on the M5 before
you plan more than a few hundred pairs, and keep it as the offline fallback.

**Budget for the live demo** (`estimate`).

- 2,000 amendments × 3 candidates = 6,000 judge calls. That is too many for "minutes".
- Gate with the cheap signals so only about 5–10% reach the judge.
- Until the judge runs, show results from the cheap signals labelled "unconfirmed".
- Precompute the 10–20 laws most likely to be named.

### Estimating the precision of published links without labels

1. **Set the threshold on LobbyPlag, out of period.** It is GDPR 2013 and mostly verbatim,
   so precision measured there *overstates* precision on paraphrase. Report it as an upper
   reference, not the claim.
2. **Run a blind audit of our own published links.**
   - Sample uniformly from the links published above the threshold, stratified by law and
     score band.
   - Two team members label each one blind to score and model output, with a fixed
     three-way rubric: real influence / standard wording / unrelated or opposite.
   - Report precision with a **Wilson 95% interval**. Brown, Cai & DasGupta (2001)
     recommend Wilson over the Wald interval for small n (`reported`).
   - Keep audit labels in a separate file from model output, and never edit scores by
     hand.
   - These are labels on our own atlas, not on the hidden test pairs. Hand-labelling the
     hidden pairs is forbidden (AGENTS.md).

Wilson 95% intervals, computed with SciPy (`measured`):

| Correct / audited | Wilson 95% |
| --- | --- |
| 10/10 | [0.722, 1.000] |
| 19/20 | [0.764, 0.991] |
| 28/30 | [0.787, 0.982] |
| 30/30 | [0.886, 1.000] |
| 45/50 | [0.786, 0.957] |
| 50/50 | [0.929, 1.000] |

So **30 audited links, all correct, are needed to claim "precision ≥ 0.89"** with 95%
confidence. Plan for about 40 audited links: two people, about 45 minutes.

### Fallbacks

- Without an API key: the cheap signals with the NLI veto, a high threshold and fewer
  published links.
- Local Qwen3-4B as the judge on the top-1 candidate only.

### Rejected

- **A reranker score as the acceptance score.** Measured: it rewards the decoys' topic
  overlap.
- **An LLM judge on whole documents.** Quoted law dominates, and cost grows with length.
- **Trusting a stated LLM probability without calibration.**
- **Discarding all text shared across many submissions.** That loses coordinated
  campaigns, which are real influence.

---

## 3. Tracing Outcomes: "Who Wins" (Part 5)

### Recommended recipe

1. **Get four texts per procedure.**
   - Commission proposal: EUR-Lex COM.
   - EP position: the committee report or first-reading text adopted by Parliament; OEIL
     links both.
   - Council mandate or general approach: Council register, when public.
   - Final act: EUR-Lex OJ.

   Four-column trilogue documents show proposal | EP | Council | compromise side by side.
   They are often only public after the deal or through an access-to-documents request, so
   use them when present; do not depend on them.
2. **Parse the structure** (Article N, paragraph n, point (x)) and align proposal articles
   to final articles. Match on number first. Then align each paragraph to the most similar
   one with greedy matching, because articles get renumbered.
3. **Decide whether an ask or amendment "won".**
   - **Adopted (verbatim)**: the change's *inserted* rare tokens are found by local
     alignment in the aligned final paragraph, and its *deleted* span is absent.
   - **Adopted in substance**: same, but via the cheap signals plus the LLM judge's
     `same_goal` label.
   - **Deletion-only**: won if the deleted span is absent from the final text but was
     present in the proposal.
   - **Not adopted**: none of these.
   - Check against the EP position first ("won in Parliament"), then the final act
     ("won in law").
   - Compare with the EP position text, not with committee vote lists. Compromise
     amendments absorb many tabled amendments, and the adopted text credits them correctly.
4. **Separate "changed the text" from "defended the status quo".**
   - An ask satisfied by the Commission proposal itself is a status-quo win.
   - Bunea (2013) found that demands for no regulation, and median positions, succeed more
     often (`reported`). Mixing the two kinds inflates wins for defenders.
5. **Who wins at institution level.** Use Laloux & Delreux's word-origin decomposition
   (`verified`, draft paper read today):
   - Pre-process: lowercase, remove punctuation and stopwords, stem.
   - Step 1: count the final-act words also in the Commission proposal, then remove them.
   - Step 2: of the rest, count words in the EP position, in the Council position, or in
     both (its own category, since priority cannot be assigned), then remove them.
   - Step 3: the remainder is trilogue-new.
   - Normalise by the length of the final act.
   - They applied it to 278 trilogue-negotiated acts, December 2012 – December 2018.
   - It is about 30 lines of code and makes a good chart for "who wins".

### Key references

- **Kreppel (1999)**, "What Affects the European Parliament's Legislative Influence? An
  Analysis of the Success of EP Amendments", *JCMS* 37(3): 521–537,
  doi:10.1111/1468-5965.00176. Success of EP amendments, hand-coded (`reported`).
- **Tsebelis, Jensen, Kalandrakis & Kreppel (2001)**, "Legislative Procedures in the
  European Union: An Empirical Analysis", *BJPolS* 31(4): 573–599. Legislative histories
  of about 5,000 EP amendments (`reported`).
- **Kardasheva (2013)**, "Package Deals in EU Legislative Politics", *AJPS* 57(4):
  858–874. 1999–2007; 2,369 issues; 1,465 proposals (`reported`).
- **Hermansson & Cross (2016)**, "Tracking Amendments to Legislation and Other Political
  Texts with a Novel Minimum-Edit-Distance Algorithm: DocuToads", arXiv:1608.06459.
  Detects insertions, deletions, substitutions and transpositions between versions
  (`verified`, abstract).
- **Cross & Hermansson (2017)**, "Legislative amendments and informal politics in the
  European Union: A text reuse approach", *European Union Politics* 18(4): 581–602.
  Minimum edit distance between Commission proposal and final act (`reported`).
- **Haag (2022)**, "Bargaining power in informal trilogues: Intra-institutional preference
  cohesion and inter-institutional bargaining success", *EUP* 23(2): 330–350. Success is
  the minimum edit distance between an institution's mandate and the trilogue outcome;
  the effect holds for the EP, not the Council (`verified`, abstract).
- **Laloux & Delreux**, "Agenda-setting, concession-trading or problem-solving? The
  institutional origins of EU legislation", EUSA conference draft (marked "do not
  quote"): https://eustudies.org/conference/papers/download/661 (`verified`). Cite it as
  a method, not for its findings.
- **Kristof, Grossglauser & Thiran (2020)**, "War of Words: The Competitive Dynamics of
  Legislative Processes", WWW '20.
  - About 450,000 edits by MEPs.
  - Predicts edit success against the inertia of the status quo and against competing
    edits on the same text.
  - Its sequel, "War of Words II: Enriched Models of Law-Making Processes" (WWW '21),
    combines explicit, latent MEP × law and text features.
  - https://infoscience.epfl.ch/record/275473 (`reported`; the PDF returned HTTP 429
    today, so I have no numbers).
- **Klüver (2009)**, "Measuring Interest Group Influence Using Quantitative Text Analysis",
  *EUP* 10(4): 535–549. Positions from Commission consultations and the final output
  placed with Wordfish and Wordscores (and hand-coding); the distance between a group's
  position and the final output measures success (`reported`).
- **Klüver (2013)**, *Lobbying in the European Union: Interest Groups, Lobbying
  Coalitions, and Policy Change*, OUP. 56 issues, 2,696 groups; issue-specific *lobbying
  coalitions*, not single groups, decide success (`reported`).
- **Bunea (2013)**, "Issues, preferences and ties: determinants of EU interest groups'
  preference attainment in the environmental policy area", *JEPP* 20(4): 552–570
  (`reported`).
- **Dür, Bernhagen & Marshall (2015)**, "Interest Group Success in the European Union:
  When (and Why) Does Business Lose?", *Comparative Political Studies* 48(8): 951–983,
  doi:10.1177/0010414014565890 (`reported`).

### Fallback

Check only whether the change appears in the EP position, as "won in Parliament". The
final act is often years later, and many 2024–2026 files have not concluded.

### Rejected

- **Wordfish-style placement on a single scale.** It works for overall positions, not for
  provision-level asks, and the jury reads specific wording.
- **Committee vote lists as ground truth.** Hard to parse and superseded by compromise
  amendments.

---

## 4. Entity Resolution of Organisations (Part 2)

### Recommended

1. **The Transparency Register ID is the primary key.**
   - Format: digits-2digits, for example `04657143399-39` (`reported`).
   - The full register downloads as XML or JSON open data (`reported`).
   - Have Your Say feedback often carries the organisation's register number. It is
     reported as a `trNumber`-style field; I could not fetch the JSON today, so check
     your downloaded records.
   - Commission meeting records published through LobbyFacts and Integrity Watch carry
     register IDs. MEP meeting declarations are usually free-text names.
2. **Normalise names.**
   - NFKC, casefold, strip accents and punctuation.
   - Drop legal-form suffixes: GmbH, AG, SE, S.A., S.p.A., Ltd, Inc, e.V., asbl, aisbl,
     AISBL.
   - Pull out the acronym in parentheses, as in "Bundesverband der Deutschen Industrie
     (BDI)".
   - Keep a table of aliases.
3. **Match in tiers.**
   - Exact match on register ID.
   - Exact match on normalised name.
   - RapidFuzz `token_set_ratio` ≥ 92 within the same country and register category, as
     a candidate.
   - Check the matches by hand only for the top actors shown in the demo.
   - RapidFuzz (MIT) is already in the catalog.
4. **Splink** (MIT, UK Ministry of Justice; Fellegi-Sunter model fitted by EM, DuckDB
   backend, runs on a laptop; `reported`) is the upgrade if you link many sources at
   scale. It is probably overkill for one day with a few thousand organisations.

### Pitfalls

- **Associations and their members** (BusinessEurope, BDI, Siemens).
  - Never merge them. Keep separate nodes with `member_of` edges.
  - Credit a link to the organisation that signed the submission, and roll up only in a
    labelled "via association" view.
- **Subsidiaries and national branches** (Google Ireland Ltd, Google LLC, Alphabet).
  Group under a parent only when there is evidence, such as register or company filings;
  otherwise keep them separate.
- **Consultancies and law firms filing for clients.** The register category "Professional
  consultancies / law firms" marks them. The client may be unnamed.
- **Duplicates over time.** Multiple or renewed registrations for one organisation, and
  renamed organisations.
- **The same name in several languages** ("Verband der Automobilindustrie" / "German
  Association of the Automotive Industry"). Acronyms help; fuzzy matching across
  languages fails.
- **Acronym collisions**: one acronym, several organisations. Never match on acronym
  alone.
- **Private citizens** (Have Your Say "EU citizen"). Do not publish their names as actors.
  Aggregate them as "citizens".

---

## 5. Public Voice Against Private Ask (Part 7: Explain)

### Recommended for a few hours

1. **Pick 5–10 actors** that have strong published links on the demo laws.
2. **Private asks**: their consultation submissions and the amendments linked to them,
   which you already have.
3. **Public voice**: 2–5 public statements per actor on the *same law*, such as press
   releases, website position pages or a CEO op-ed. Choose the URLs by hand, record them
   and store the text.
4. **Claim extraction by LLM**, with a structured output per claim:
   - `provision` (article or topic)
   - `stance` on −2..+2: from "stronger, stricter regulation" to "weaker, delay, exempt"
   - `quote` (exact span, checked by substring as in section 2)
5. **Compare by provision.** Flag "says X publicly, asks Y privately" only when both sides
   have checked quotes and the stances differ by 2 or more.
6. **A person reviews every flag shown.** There will be few.

**InfluenceMap's LobbyMap is the precedent** (`verified` in part, from the FAQ):

- Each piece of evidence is scored on a five-point scale from +2 (strongly supporting) to
  −2 (opposing).
- The scale is benchmarked against external references (the IPCC 1.5 °C report, EU
  Commission ambition), not their own view of good policy.
- Recent evidence gets more weight.

The following parts are `reported` from secondhand pages:

- The evidence includes legislative consultations, websites, financial filings and CEO
  messaging.
- The Organisation Score runs 0–100: below 50 misaligned, 50–75 mixed, above 75 aligned.
- Engagement Intensity runs 0–100: above 12 active, above 25 highly active.

Their split between what a company says and what it does in direct lobbying is the
framing to borrow, with the benchmark adapted to the chosen law: the Commission proposal
as 0, stricter as +, weaker as −.

**Automatic stance is hard.** Morio & Manning (NeurIPS 2023 Datasets & Benchmarks), "An
NLP Benchmark Dataset for Assessing Corporate Climate Policy Engagement": 10k LobbyMap
documents; Longformer was best but left large headroom (`reported`). That justifies human
review of every flag.

### Fallback

No stance model. Show, per provision, the actor's public quote next to its private ask,
and let the reader judge.

### Rejected

- **Automatic stance scores for all actors.** Unreliable without analysts.
- **Scraping social media.** Terms of service and time.
- **Whole-document sentiment.** It does not tell you what was asked of which provision.

---

## 6. Forecasting (Part 7: Forecast)

### Target A: which open asks land

**Features.** Use only those knowable before the outcome date:

- **Direction.** Status-quo defence or change, relative to the Commission proposal
  (Bunea 2013).
- **Coalition breadth.** The number of distinct organisations, and of distinct actor
  types, making the same ask. Cluster asks by change similarity; Klüver (2013) finds
  coalitions decide success.
- **Counter-coalition.** The number of organisations asking the opposite.
- **Parliamentary uptake.**
  - A matching amendment was tabled.
  - The tabling MEP's role (rapporteur, shadow; from OEIL) and group size.
  - Above all, whether the **rapporteur's draft report** contains the change; that is
    likely the strongest single signal (`estimate`, unmeasured).
- **Council.** The general approach contains it, when available before the trilogue.
- **Actor.** Type (business, NGO, public authority; Dür et al. 2015), declared spend
  band, and meetings with the Commission and MEPs before the outcome (register).
- **Text.** Specificity and length of the ask. Kristof et al. (2020, 2021) combine edit,
  MEP and law features with text.

**Model.** Logistic regression, which gives calibrated output and readable
coefficients. Use HistGradientBoosting only if it beats the logistic model on the same
folds. Baselines: the base rate, and the rule "the rapporteur's draft includes it".

**Honest backtest.**

- Split by **procedure completion date**: train on procedures concluded before a cutoff
  (for example 1 January 2023) and test on those concluded after.
- Group by procedure, so no procedure appears on both sides.
- Build features **as of** the forecast date, from documents dated before it, never from
  the final act.
- Report AUC, Brier score and precision@k against the baselines, on the same split and
  seeds.

**Right-censoring.** Files from 2024–2026 are often unfinished. Use "reached the EP
position" as an interim outcome, or drop open procedures from the training labels.

### Target B: who is rising or fading

For each actor and year, compute links published, asks that won and the win rate.

- **Shrink the win rate** with a beta-binomial prior fitted over all actors
  (method-of-moments α and β), so 1/1 does not top the chart.
- **Trend**: the difference between the last two years and the two before, with a
  bootstrap or Beta-posterior interval.
- Call an actor "rising" only if the interval excludes 0; otherwise label it
  "insufficient data".
- Show register meeting counts and declared spend next to wins. That addresses the
  brief's "who actually wins, not who spends most" (`estimate`: standard statistics,
  untested on our data).

### Rejected

- **Random k-fold over asks.** It leaks the same law and the same coalition across folds.
- **Features from the final text.**
- **"Rising" from raw counts.** Counts grow with the number of consultations, not with
  influence; normalise per consultation the actor took part in.

---

## 7. Topic Classification

### Recommended: do not classify laws, read their codes

- **OEIL procedure files carry a subject classification**: the Legislative Observatory
  page links its subject-classification list (`verified`).
- **EUR-Lex/CELLAR metadata attach EuroVoc descriptors** to legal acts (`reported`).
- Submissions inherit the topic of the initiative or procedure they answer, and
  amendments inherit their procedure's.
- If per-article topics are needed, use a zero-shot LLM over about 20 top-level OEIL
  subjects, a short fixed list.

### Fallback for documents without descriptors

- **PyEuroVoc** (Avram, Pais & Tufiș, RANLP 2021): EuroVoc classifiers fine-tuned for 22
  languages; outperforms JRC's JEX; code and models are open (`reported`).
- **MultiEURLEX** (Chalkidis, Fergadiotis & Androutsopoulos, EMNLP 2021): 65k EU laws in
  23 languages with EuroVoc labels; shows that zero-shot transfer across languages is
  weak without adaptation (`reported`).

### Rejected

- **Training a EuroVoc classifier today.** It has thousands of labels and the
  descriptors already exist.
- **Zero-shot over all of EuroVoc.** Too many labels for reliable zero-shot.

---

## 8. Multilinguality

### Recommended

1. **Use the EU's official translations, not machine translation.**
   - EP committee amendments, Commission proposals and final acts are published in all
     official languages (`reported`; verify that your Parltrack and EUR-Lex fetch can
     return the other language versions).
   - Compare a German submission with the **German** text of the amendment and the
     proposal for every lexical signal: BM25, rare n-grams, Smith-Waterman, characters.
     The verbatim evidence then stays verbatim.
2. **Retrieve with dense embeddings across languages** (BGE-M3 or Qwen3-Embedding, both
   100+ languages) when the language of the submission's version is unavailable.
3. **Detect language** with Lingua (Apache-2.0, in the catalog).
4. **Use machine translation for display only.** The jury reads both texts side by side
   in English. OPUS-MT ships one model per language pair; licences vary by model
   (Apache-2.0 confirmed for de→en, others may be CC-BY-4.0), so check each card. Claude
   reads the source languages directly, so the judge does not need translation.

### Rejected

- **Lexical-overlap signals on machine-translated text against original text.**
  Translation introduces paraphrase, so real copies are lost and spurious overlap appears.
- **NLLB-200.** CC-BY-NC-4.0; non-commercial.
- **Translating everything up front.** Slow, and unnecessary given the official
  translations.

---

## What Is Not Verified (Read Before Quoting)

- Speeds of BGE-M3, Qwen3-Embedding, MLX and local Qwen3-4B on this M5. Only mpnet
  encoding and NumPy search were measured.
- Every number in the War of Words papers. Their PDFs returned HTTP 429.
- The exact name of the Have Your Say field for the register number.
- The InfluenceMap score bands and engagement-intensity cut-offs, which came from search
  snippets.
- The bibliographic details of Kreppel, Tsebelis et al., Kardasheva, Cross & Hermansson,
  Klüver, Bunea and Dür et al. came from catalogue records; I did not read the papers
  today.
- Claude prices come from a reference cached 25 September 2026. Check the pricing page
  before quoting cost per pair.
- The boilerplate cut-offs (0.5% of documents, 20 authors), the RapidFuzz threshold of
  92 and the gate rate of 5–10% are starting values to tune on LobbyPlag, not findings.

## References (URLs)

- BGE-M3 model card: https://huggingface.co/BAAI/bge-m3 (`verified`)
- Qwen3-Embedding-0.6B model card: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B (`verified`)
- EmbeddingGemma-300M: https://huggingface.co/google/embeddinggemma-300m (`reported`)
- BM25S: Lù, *BM25S: Orders of magnitude faster lexical search via eager sparse scoring*,
  2024, https://arxiv.org/abs/2407.03618; code https://github.com/xhluca/bm25s (`reported`)
- Splink: https://www.adruk.org/news-publications/news-blogs/splink-free-software-for-probabilistic-record-linkage-at-scale (`reported`)
- Brown, Cai & DasGupta, "Interval Estimation for a Binomial Proportion", *Statistical
  Science* 16(2), 2001, https://projecteuclid.org/euclid.ss/1009213286 (`reported`)
- Haag 2022: https://ideas.repec.org/a/sae/eeupol/v23y2022i2p330-350.html (`verified`, abstract)
- Haag, ECPR 2020: https://ecpr.eu/Events/Event/PaperDetails/55250 (`verified`, abstract)
- Laloux & Delreux draft: https://eustudies.org/conference/papers/download/661 (`verified`)
- DocuToads: https://arxiv.org/abs/1608.06459 (`verified`, abstract)
- Cross & Hermansson 2017: https://ideas.repec.org/a/sae/eeupol/v18y2017i4p581-602.html (`reported`)
- Kristof et al. 2020: https://infoscience.epfl.ch/record/275473 (`reported`)
- Kreppel 1999: https://ideas.repec.org/a/bla/jcmkts/v37y1999i3p521-537.html (`reported`)
- Tsebelis et al. 2001: https://ideas.repec.org/a/cup/bjposi/v31y2001i04p573-599_00.html (`reported`)
- Kardasheva 2013: https://ideas.repec.org/a/wly/amposc/v57y2013i4p858-874.html (`reported`)
- Klüver 2009: https://ideas.repec.org/a/sae/eeupol/v10y2009i4p535-549.html (`reported`)
- Klüver 2013 book: https://academic.oup.com/book/11574 (`reported`)
- Bunea 2013: https://www.uib.no/en/persons/Adriana.Bunea (`reported`)
- Dür, Bernhagen & Marshall 2015: https://aura.abdn.ac.uk/items/fcea3132-3a2b-46f8-b3ea-799ce7aa84ab (`reported`)
- Casas & Rodilla Lázaro 2025: https://ecpr.eu/Events/Event/PaperDetails/82414 (`verified`, abstract)
- InfluenceMap FAQ: https://europe.influencemap.org/faq (`verified`, in part)
- Morio & Manning 2023: https://proceedings.neurips.cc/paper_files/paper/2023/hash/7ccaa4f9a89cce6619093226f26b84e6-Abstract-Datasets_and_Benchmarks.html (`reported`)
- PyEuroVoc: https://aclanthology.org/2021.ranlp-1.12 (`reported`)
- MultiEURLEX: https://aclanthology.org/2021.emnlp-main.559 (`reported`)
- OEIL subject classification: https://oeil.europarl.europa.eu/oeil/en/find-out-more (`verified`)
