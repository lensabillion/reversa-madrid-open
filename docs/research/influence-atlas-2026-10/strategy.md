# The Influence Atlas: how to win Challenge 03 today

Prepared Saturday 3 October 2026, morning, for the demo at 19:30 CEST.

Status tags:
- `verified`: I fetched and read the primary page today. It was read through a summarising fetch tool, so check exact wording before quoting it.
- `reported`: taken from search-result snippets or secondhand coverage. I did not read the primary source.
- `unsure`: my own recollection, or sources that conflict. Check it before using it.

Repo facts I observed (read-only): `data/` holds `parltrack`, `lobbyplag`, `idf.npz`, `emb-cache`, a single `hys/sample.pdf`, and a single EUR-Lex text (GDPR, `32016R0679`). **The consultation (Have Your Say) documents and the final-law texts for 2019–2026 are therefore not downloaded yet.** That is today's biggest schedule risk (see §6).

There is also a mismatch to settle in the first ten minutes. `AGENTS.md` and `docs/implementation-status.md` describe CSV deliverables (60 pairs, 20 proposals) and a rule that hand-labelling hidden test pairs disqualifies the team. The brief summary for "The Influence Atlas" says "no data handed out, no labels" and lists different deliverables: a graph, a report and a repo. An untracked `docs/brief/The Influence Atlas — Challenge Brief.pdf` exists. Treat it as the current brief and update the repo docs, or the agents will optimise for the wrong deliverable.

---

## 1. The rubric as a strategy

The organising principle is that **precision beats coverage on every live check.** The jury samples what we show, so only show what holds up. Put everything else behind a "tentative" toggle with an honest label.

### Real links (25): the jury opens 3 random edges and reads both texts

**What the jury will do.** Click three edges, probably including one we did not choose and one on a law they know. They will read the lobby passage and the amendment side by side and ask whether this is standard wording.

**How it fails live.**
1. The shared span is EU boilerplate, for example "Member States shall ensure that", "without prejudice to", or "in accordance with Article".
2. The lobby paper **quotes the Commission proposal** and the amendment keeps that same proposal text. Both then match the base text, not each other. This is the most common false positive in this domain.
3. Direction is reversed: the lobby paper postdates the amendment and is reacting to it.
4. A link is shown without the final article, so the "won" claim is unsupported.
5. The match is a long list of defined terms or annex codes, such as CN codes in CBAM or NACE codes.

**What maximises points.**
- **Match on the change, not on the document.** This is already our core idea. Compute the delta of each amendment against the Commission text: Parltrack amendments carry the "Text proposed by the Commission" and "Amendment" columns. Only inserted or replaced tokens count as evidence. Then **subtract base text from the lobby passage** before matching.
- **Rarity filter.** Score shared spans by corpus document frequency over the roughly 540k amendments (`idf.npz` exists). Require at least one shared span of 8 or more tokens that appears in fewer than N other amendments. Show the number in the UI, for example: "this 11-word phrase appears in 0 of 540,112 other amendments". That one number answers the boilerplate objection before the jury raises it.
- **Timing gate.** The lobby document date must be no later than the amendment tabling date. Show both dates on the edge.
- **Three tiers, and only the top tier is shown by default.**
  - *Verbatim insertion*: a rare span copied into the change.
  - *Reworded*: semantic match on the change plus some rare-token overlap. This needs a semantic model; label it "reworded, model-scored".
  - *Same direction only*: hide this tier by default.
- **Every edge is one evidence card:** the ask (with a PDF page link), the amendment (number, MEP, committee, date, Parltrack link), the final article (EUR-Lex link with article number, or "not in final law": heard, not won). Highlight the matched words and grey out the base text.
- **Self-audit before the demo.** Each team member reads 20 random top-tier edges. Report the measured precision in the report and use it to set thresholds, not to hand-edit edges. Disclose this audit in the methodology. Hand-picking edges for display would contradict "no code changes" in spirit.

### Any law (20): the jury names a law; we show who shaped it, with no code changes

**What the jury will do.** Name a famous file such as the AI Act, the DMA, CSDDD or the Nature Restoration Law. Or they may test robustness with an odd one: the PFAS restriction (not a legislative procedure), the MDR (adopted in 2017; the 2023 extension used the urgent procedure without committee amendments), an implementing act, or a non-English nickname such as "Lieferkettengesetz" or "Green Claims".

**How it fails live.**
- The name does not resolve.
- The pipeline runs live and venue Wi-Fi stalls on PDF downloads.
- A law has no consultation documents and we show an empty or broken page.
- A lobby paper is in German or French and our English lexical scorer silently finds nothing.
- The law predates 2019.

**What maximises points.**
- **A law resolver**, as a precomputed alias table: Parltrack dossier title, procedure reference (for example 2021/0106(COD)), CELEX, an acronym list, and nicknames in EN/DE/FR/ES. Fuzzy search box with autocomplete.
- **Precompute every 2019–2026 COD procedure** that has committee amendments. Live view then becomes a lookup in milliseconds. Keep an on-demand path for an unlisted procedure, with a progress bar, a hard time cap, and cached downloads.
- **Layered results, so a law is never "empty":**
  - The amendment layer from Parltrack covers every procedure: who tabled, identical amendments across MEPs, what survived.
  - The consultation layer covers procedures where Have Your Say feedback exists.
  - The final-text layer covers adopted laws.
  - Each missing layer gets an honest badge, such as "No public consultation documents for this file (urgent procedure)" or "Not a legislative procedure: REACH restriction via ECHA; shown: consultation submissions only".
- **Language.** Detect the language for each document. Score non-English documents with a multilingual embedding if one is cached; otherwise label them "not analysed (DE)" and count them. Never imply absence.
- **Offline-first.** All data on the laptop, a phone hotspot as backup, and a recorded screen capture of the "any law" flow as a last resort.

### Insight (25): something non-obvious the jury can check on the spot

Give one finding per question (§3). Each needs a number, a named actor or law, and **one click to the evidence**. Avoid insights that reduce to "big spenders win". The brief explicitly calls that weak, so show the residual instead.

### Report (15): publishable as is; the repo is rerunnable

Write it in a journalist's register (§4), with a methodology section, measured precision, limitations, and permalinks to edges. The README needs a one-command rerun, a small `--sample` mode that finishes in under 5 minutes, and a provenance table (§5).

### Ambition (15): all of Europe since 2019, plus a reasoned forecast

- Put a coverage banner on the landing page: "N procedures, M amendments, K consultation submissions, 2019–2026, 3 institutions". Parltrack gives EP-wide coverage cheaply, so lead with it.
- Forecast. Two parts, both explainable:
  1. **Rising and fading actors:** year-over-year change in heard and won counts per actor and topic, with the reasons shown.
  2. **Which asks land in files under negotiation now.** A simple logistic model trained on adopted laws up to 2023 and tested on 2024–25.
     - Features: whether the ask already appears in the Commission proposal, the Council general approach and/or the EP mandate; the actor's past win rate in the topic; how many distinct actors make the same ask; whether the ask deletes, delays or exempts rather than adds; and the rapporteur group.
     - Report AUC on the held-out years.
- Candidate live files to forecast on, as of late 2025. Re-check their status today.
  - The **Digital Omnibus**, proposed 19 November 2025, which touches the GDPR, AI Act and Data Act. Reported: it delays high-risk AI rules to December 2027 at the latest.
  - The **Automotive package**, of 16 December 2025, which would cut the 2035 cars target from 100% to 90%.
  - Both are `reported`: [White & Case](https://www.whitecase.com/insight-alert/eu-digital-omnibus-what-changes-lie-ahead-data-act-gdpr-and-ai-act), [Akin](https://www.akingump.com/en/insights/alerts/steering-toward-2035-eus-automotive-sector-gets-a-package), [DieselNet](https://dieselnet.com/news/2025/12eu.php).
  - They are ideal because the same actors (Big Tech, DigitalEurope, ACEA, VDA) appear in the historical layer, so the forecast has a track record to cite.

---

## 2. What is already publicly known (validation cases and stories)

"Text?" says whether the source documents **specific copied or adopted wording**, which makes it a direct validation case. Otherwise the source only covers meetings, spending, or positions that align with outcomes.

| Law | Claim | Source | Status | Text? |
|---|---|---|---|---|
| GDPR (2012–13, before 2019; our practice set) | Dozens of IMCO/ITRE amendments copied word for word from Amazon, eBay, AmCham EU and EBF papers. Named MEPs with more than 22–25% copied content: Harbour, Karim, Chichester. Basis of LobbyPlag. | [Privacy International](https://privacyinternational.org/press-release/1470/amazon-and-ebay-lobbyists-found-be-writing-eu-data-protection-law-copy-paste) | reported | **Yes**: our calibration set (172 verified links in repo) |
| Euro 7 (2022–24) | ACEA's head of public affairs emailed a request to restore Euro 6 limits. Czech Renew MEP Ondřej Kovařík reportedly copy-pasted it into an amendment circulated for the ENVI vote of 12 Oct 2023. No amendment number is given. A 1 June 2022 meeting of the ACEA board (BMW CEO Zipse) with DG GROW Director-General Kerstin Jorna was reportedly missing from the register. | [EDJNet/Voxeurop, 13 Dec 2023](https://europeandatajournalism.eu/?p=242782) | verified (article read; spelled "Kovalik" there; other coverage says Breton's cabinet, so roles conflict) | **Yes, but the lobby text is an FOI'd email, not public.** We can check whether the Kovařík ENVI amendment exists in Parltrack and matches ACEA's *public* Euro 7 position paper ([ACEA](https://www.acea.auto/?p=14882)). Strong demo story if it does. |
| CSDDD / Omnibus I (2024–26) | ExxonMobil reportedly held at least 25 meetings with the Commission and EP (Jan 2024 – Jul 2025) and threatened its EU investments. Three of its four priorities ended up in the Commission's Omnibus proposal, the Council position and rapporteur Jörgen Warborn's position. | [SOMO, 2 Oct 2025](https://www.somo.nl/how-big-oil-kills-sustainability-and-climate-legislation/) (403 for me), via [BHRRC](https://www.business-humanrights.org/en/latest-news/somo-exxonmobil/) | reported (BHRRC summary read; SOMO itself not readable) | **Partial**: asks mapped to outcomes, no side-by-side text. Excellent ask → final-text test. Final Omnibus I was published in the OJ on 26 Feb 2026 ([Frank Bold](https://en.frankbold.org/news/epp-sides-with-the-far-right-to-gut-the-eus-sustainability-framework-in-the-omnibus-i-vote), reported). |
| Omnibus I process | The EU Ombudsman found maladministration (27 Nov 2025): consultation shortened, under 24 hours over a weekend, no climate consistency records. The EP mandate on 13 Nov 2025 passed 382–249 with EPP and far-right votes. | [The Good Lobby](https://thegoodlobby.eu/omnibus-i-found-against-eu-law/), [ESG Today](https://www.esgtoday.com/eu-watchdog-says-commission-failed-to-follow-procedures-in-cutting-sustainability-reporting-rules/), [Frank Bold](https://en.frankbold.org/news/epp-sides-with-the-far-right-to-gut-the-eus-sustainability-framework-in-the-omnibus-i-vote) | reported | No. It is a "HOW/channels" story: skipped consultation means influence moves to meetings. |
| AI Act (2021–24) | US Big Tech lobbied to keep general-purpose AI out of scope ("The lobbying ghost in the machine", Feb 2023). Mistral (Cédric O) and Aleph Alpha worked through the French and German governments. Aleph Alpha held 12 meetings with German ministers or state secretaries (Jun–Nov 2023). 78% of high-level Commission AI meetings in 2023 were with corporate interests. | [CEO "Trojan horses", 11 Mar 2024](https://corporateeurope.org/en/2024/03/trojan-horses-how-european-startups-teamed-big-tech-gut-ai-act); [CEO ghost](https://corporateeurope.org/en/2023/02/lobbying-ghost-machine); [CEO Nov 2023](https://corporateeurope.org/en/2023/11/big-tech-lobbying-derailing-ai-act) (cites 86% of high-level meetings with industry: a different period or base) | verified (Trojan horses); reported (others) | No: meetings and outcome alignment. A FR/DE/IT non-paper (Nov 2023) proposed "mandatory self-regulation through codes of conduct" for foundation models ([BHRRC](https://www.bhrrc.org/en/latest-news/eu-france-germany-and-italy-push-for-codes-of-conduct-without-a-sanction-regime-for-foundation-models-in-ai-act-according-to-media-reports/), reported). Testable: do "codes of practice" for GPAI in the final Act echo Mistral/DigitalEurope HYS submissions? Council channel, so it does not appear in EP amendments. |
| DMA/DSA (2020–22) | 612 organisations spent at least €97m a year lobbying on digital policy. 10 firms account for €32m: Google, Facebook, Microsoft, Apple, Amazon, Huawei, IBM, Intel, Qualcomm, Vodafone. | [CEO/LobbyControl, Aug 2021](https://corporateeurope.org/en/2021/08/big-tech-takes-eu-lobby-spending-all-time-high) | reported | No: spending. Useful as the "spend" baseline for the wins-versus-spend residual. |
| Nature Restoration Law (2022–24) | About 75% of farm-union meetings on Farm to Fork, NRL and SUR were with Copa-Cogeca or its members, outnumbering NGO meetings 8 to 1. Copa-Cogeca called for rejection. | [DeSmog, 4 Oct 2023](https://www.desmog.com/2023/10/04/revealed-meetings-blitz-between-big-ag-and-anti-green-lawmakers-in-europe/) | reported | No. Good **heard ≠ won** case: the EPP rejection push failed. The EP adopted a weakened text in July 2023 and the law was adopted in 2024 (unsure on exact dates; check EUR-Lex). Compare Copa-Cogeca's asks with the ENVI/AGRI amendments and the final text (for example, removal of the agricultural-land article: unsure, check). |
| EUDR (2023–26) | Copa-Cogeca and Cepi issued joint delay statements in 2024. On 14 Nov 2024 the EP adopted EPP amendments: a 12-month delay plus a new "no-risk" country category. In trilogue (Dec 2024) the no-risk category was **dropped** and the delay kept. A second one-year delay to 30 Dec 2026 followed (agreement 4 Dec 2025), plus some simplifications. | [InfluenceMap](https://influencemap.org/insight/Repeated-Delays-Hinder-EU-Deforestation-Regulation), [FoodNavigator](https://www.foodnavigator.com/Article/2024/12/02/classification-faced-push-back-from-member-states/), [Earthsight](https://www.earthsight.org.uk/news/amendments-scrapped), [Baker McKenzie](https://www.bakermckenzie.com/en/insight/publications/alerts/2025/12/european-union-provisional-agreement-on-eudr-one-year-postponement), [Mongabay](https://news.mongabay.com/short-article/2026/01/eudr-antideforestation-law-officially-delayed-for-second-year-in-a-row/) | reported | **Partial, and the best heard-versus-won demo:** a tabled and adopted EP amendment ("heard") that lost in trilogue, next to a delay ask that won twice. Both are visible in public texts. |
| CBAM (2021–23) | Heavy industry (Eurofer, ArcelorMittal, thyssenkrupp, CEMBUREAU, VCI/BASF/Cefic, Eurometaux) won a slower phase-out of ETS free allocation than proposed, with 48.5% phased out by 2030 and the phase-out running 2026–2034. Chemicals were excluded from scope. Export rebates were **not** won despite intense lobbying. | [InfluenceMap CBAM](https://europe.influencemap.org/policy/EU-Carbon-Border-Adjustment-Mechanism-430) | verified (page read; it does not attribute specific text) | Partial: asks matched to outcomes. Shows a "lost ask" (export rebates) next to a "won ask". |
| CO2 standards for cars (2025) | After the Strategic Dialogue, the Commission (Mar 2025) proposed three-year averaging of 2025–27 compliance, adopted in May 2025. VDA pushed for a phase-in; ACEA called it "a step in the right direction". Then the Automotive package (Dec 2025) proposed cutting the 2035 target from 100% to 90%. | [InfluenceMap LDV CO2](https://europe.influencemap.org/policy/EU-Light-Duty-Vehicles-CO2-targets-3481), [NewMobility](https://newmobility.news/2025/05/28/eu-parliament-gives-the-nod-on-softened-eu-co2-targets/), [Akin](https://www.akingump.com/en/insights/alerts/steering-toward-2035-eus-automotive-sector-gets-a-package) | reported | No. **Forecast case:** ACEA and VDA asks on the 2035 file, which is under negotiation now. |
| PFAS universal restriction (REACH, 2023–) | Forever Lobbying Project (Jan 2025; 46 journalists, 16 countries): hundreds of industry actors across about 15 sectors. CEO names Chemours as most involved. Clean-up cost without restriction is about €2 trillion over 20 years. | [Forever Lobbying Project](https://foreverpollution.eu/lobbying/), [Food Packaging Forum](https://foodpackagingforum.org/news/coordinated-lobbying-campaign-targeted-european-pfas-regulation-reports) | reported | No. It is **not a COD procedure** (ECHA/REACH), so it is the archetypal "any law" edge case for an honest empty state. ECHA consultation comments are public and could be ingested later. |
| Data Act (2022–23) | DigitalEurope, Siemens and SAP asked the Commission to "pause and rethink" and demanded a trade-secret refusal ground. A trade-secret safeguard (an important but not absolute defence) was added in trilogue. EP approval came on 9 Nov 2023. | [DigitalEurope joint statement PDF](https://cdn.digitaleurope.org/uploads/2023/06/Data-Act-joint-statement-June-2023.pdf), [Freshfields](https://technologyquotient.freshfields.com/post/102isit/the-data-act-and-the-eus-digital-agenda-striking-a-balance-in-trade-secret-pro) | reported | **Good text case:** the public joint statement exists as a PDF, and the final Data Act has trade-secret articles (Art. 4 and 5, unsure on numbering). It is a trilogue win, so it is a "won without an EP amendment" path. |
| MDR (2017; extension 2023) | After a year of medtech lobbying, the Commission repeatedly conceded delays. The 2023 extension was fast-tracked. | [Citeline](https://medtech.citeline.com/MT148272/Entire-EU-Medtech-Industry-Throws-Weight-Behind-Argument-To-Structurally-Reform-MDR-And-IVDR) | reported | No. Edge case: pre-2019 base law and urgent procedure. |
| Chips Act | No primary source checked today. | — | unsure | Skip unless time allows. |
| Academic | Cross & Hermansson (2017), *European Union Politics* 18(4): 581–602, use minimum-edit-distance text reuse to measure change from proposal to outcome. This is the methodological precedent for our "change, not document" approach; cite it. Klüver's work on lobbying success in EU consultations (*Lobbying in the European Union*, OUP 2013) measures success as preference attainment, not wording; cite it for the "reworded influence" argument (unsure on exact title). | [RePEc](https://ideas.repec.org/a/sae/eeupol/v18y2017i4p581-602.html) | reported | Method, not cases. |

**Takeaway for the demo story.** Almost all public investigations since 2019 document *meetings and outcome alignment*, not text. Copy-paste evidence (GDPR 2013, Euro 7 2023) is rare and relies on leaks or FOI. Our pitch: *"Journalists find these one leak at a time. We check every amendment since 2019 against every public submission, and show the receipts."*

---

## 3. Candidate non-obvious insights (computable today)

Priority order: **A, B, C** first. They need only Parltrack plus what is on disk, or are cheap to add.

| # | Insight (hypothesis to test, not a claim) | Data needed | How the jury checks it in 30 seconds |
|---|---|---|---|
| **A** | **Ghost-written amendments.** Identical or near-identical amendment text tabled by MEPs from *different political groups* on the same file is the fingerprint of an external draft. Rank files and actors by this, then trace clusters to a lobby paper where we have one. Answers HOW and WHO with no lobby documents needed. | Parltrack amendments only: normalise, MinHash or hash, cluster across group affiliation. | Click a cluster: amendments 123 (EPP) and 456 (S&D) with the same 40 words, both Parltrack links. |
| **B** | **Heard is not won.** The share of lobby asks that MEPs tabled that also survive into the final law, by actor type (company, trade association, NGO, union). Expect a large gap. Who converts "heard" into "won" best is often not the loudest. | Amendment layer, final-text layer (EUR-Lex), actor-type mapping (Transparency Register category). | Pick an actor: 37 asks tabled, 4 in the final law, each with an article link. EUDR "no-risk" category = heard, lost; delay = won. |
| **C** | **Wins above budget.** Regress won asks on log lobby spend; list the largest positive residuals (and the big spenders with few wins). This is what the brief calls "great". | Wins, Transparency Register/LobbyFacts spend. Use a spend band if the exact figure is missing. | Actor card: "€X spend, rank 140; won asks rank 9", with links to the register entry and the edges. |
| D | **Subtraction wins.** Asks that delete, delay, exempt or raise a threshold are adopted at a higher rate than asks that add obligations. The winning playbook is to remove, not to write. | Classify ask type by keywords and diff direction (deletion-heavy amendments). | Filter edges by "deletion" and compare the two rates. Spot-check two. |
| E | **Second door (the Council).** Asks with no matching EP amendment that still land in the final text, as with Data Act trade secrets. That is where influence ran through member states. | Final text compared with the Commission proposal and EP amendments; Council general approach, if downloaded. | Three-column view: proposal, EP amendments (no match), final article (match). |
| F | **Timing.** Asks made at the call-for-evidence stage, before the proposal, land in the Commission text more often than asks made after it. Early movers write the base text. | HYS feedback dates for both stages; Commission proposal text. | Two counts plus one example where the ask phrase appears in the proposal itself. |
| G | **Coalitions.** Asks made by 3 or more distinct actors, especially cross-sector (industry plus unions), win at a higher rate than lone asks. | Cluster semantically equivalent asks across submitters. | Click a coalition ask: 5 signatories, 1 final article. |
| H | **Says vs asks.** Actors whose submissions open with "we support the objectives" but whose concrete asks are mostly delete or delay. This is the TOWARDS-what gap between public and private positions. | First paragraph stance compared with the ask type distribution. Crude, so label it "indicative". | Open the paper: the support line on page 1, the deletion asks on page 3. |

Guardrail for C and the MEP rankings: say "text overlap" or "tabled wording matching", never "copied" or "corrupt". Show the evidence card and the rarity number. Rank MEPs only on a rate per amendment tabled, never on raw counts.

---

## 4. Demo script (5 minutes) and report outline

### Demo, minute by minute

Rehearse twice and record a backup capture.

- **0:00–0:30 Hook.** "Since 2019 the European Parliament has tabled about 540,000 committee amendments. Investigations have found copied lobby text one leak at a time: GDPR in 2013, Euro 7 in 2023. We checked all of them."
  - Show the coverage banner.
  - State the trap and our answer in one line: "similar wording proves nothing, so we only count wording that is *new in the amendment* and *rare across the corpus*."
- **0:30–1:30 One edge, read live.** Open the strongest evidence card, ideally on a law the jury knows (EUDR or CSDDD).
  - Lobby passage, then amendment delta, then final article.
  - Point to the rarity line ("appears in 0 of 540k other amendments") and the dates.
  - Then invite them: "Pick any edge." Default view shows top-tier edges only.
- **1:30–2:30 Any law.** Hand the keyboard to the jury.
  - The resolver autocompletes; the precomputed result appears in under 2 seconds.
  - Point out the layer badges and an honest empty state, for example PFAS: "REACH restriction, no EP amendments; consultation layer only".
- **2:30–3:45 Five answers, about 15 seconds each.** One finding per question, each with one click to evidence:
  - WHO: wins above budget.
  - WHAT: topics by won asks.
  - TOWARDS what: subtraction wins, or says vs asks.
  - HOW: ghost-written cross-group amendments and the second door.
  - NEXT: as in the following item.
- **3:45–4:30 Forecast.** Rising and fading actors, with reasons. For one file under negotiation (the Automotive package or the Digital Omnibus), list the 3 asks most likely to land, each with its features: already in the Council text, coalition of 5, past win rate. Give the held-out AUC.
- **4:30–5:00 Trust.** Measured precision of top-tier edges from our own audit, `make atlas` reruns everything, licences, link to the report. Close: "Every edge has its receipt."

### Report outline (what a journalist would publish)

Length: 1,800–2,500 words plus 3 tables and 2 charts. Format: a web page in the repo (`report/`) plus PDF.

1. **Headline and standfirst.** One sentence each, with a number.
2. **Five findings**, one per question. Each finding has a number, a named actor or law, and 2–3 evidence permalinks (`/edge/<id>`, which shows the lobby page, amendment and article), plus "what this does not show".
3. **Case studies (2–3).** For example, EUDR (heard vs won), Omnibus I (asks to outcome, consultation skipped), and one AI Act or Data Act trilogue win.
4. **League tables.** Top actors by won asks, by topic and year, with spend alongside.
5. **What comes next.** The forecast, with reasons and the validation metric.
6. **Methodology.**
   - Data sources with retrieval dates.
   - The change-based matching.
   - Rarity thresholds.
   - Tier definitions.
   - The self-audit (sample size, precision, inter-rater agreement if 2 people overlapped).
   - Forecast training and test split.
7. **Limitations.**
   - Public documents only: meetings and emails are invisible, so absence of an edge is not absence of influence.
   - Reworded influence is model-scored and lower confidence.
   - Council and trilogue opacity.
   - Language coverage percentage.
   - Actor-name resolution errors.
   - Overlap is not proof of causation: an MEP may agree independently.
8. **Right of reply and corrections.** Named organisations were not contacted within the hackathon. Publish a corrections address.
9. **Data and licences** (§5).

---

## 5. Open-source credibility

- **Code.** Use **Apache-2.0**: a permissive licence with an explicit patent grant and contribution terms, attractive if Reversa or others build on it. MIT is fine if the team wants maximum brevity. Either satisfies "open licence". Add `LICENSE` and SPDX headers.
- **Report and our own annotations.** Use **CC BY 4.0**.
- **Derived database: ODbL obligations.** Parltrack states its dumps are under the Open Database License v1.0 ([parltrack.eu/dumps](https://parltrack.eu/dumps); `reported`, check the page).
  - Any **publicly used derivative database**, such as our graph export built from Parltrack amendments, must be offered under **ODbL** (share-alike) with attribution: "Contains information from Parltrack, available under the ODbL".
  - **Produced works** (charts, the report) can be CC BY 4.0, but must carry a notice that they use a Parltrack-derived database under ODbL.
  - So the license matrix is: code Apache-2.0, graph data ODbL, report CC BY 4.0.
- **Other sources (`unsure` on exact terms; check each).**
  - EUR-Lex and EP documents: reuse is allowed with source acknowledgement under Commission Decision 2011/833/EU and the EP legal notice.
  - Transparency Register: published as open data on data.europa.eu.
  - Have Your Say attachments: copyright stays with the authors. Store and quote short excerpts as evidence; link to the original instead of redistributing PDFs.
  - LobbyFacts: check its terms.
- **Privacy.** Exclude submissions by **individual citizens**; analyse organisations only. MEPs are public office holders. Avoid naming individual lobbyists beyond register data.
- **README for a one-command rerun.**
  - `make atlas`: download, with dated and checksummed sources in `data/provenance.json`; build; serve.
  - `make atlas-sample`: about 5 laws, under 5 minutes, on a clean machine. (Not built. The rerun path that exists is `make setup && make atlas LAW='AI Act'`, one law per run; note added 3 October.)
  - State hardware and timings measured today.
  - Provenance table columns: source, URL, retrieval date, licence, SHA-256, record count.

---

## 6. Risks and cut lines

**Biggest risk now.** The consultation PDFs and final texts are not on disk; only GDPR and one sample are. Start bulk downloads immediately, in the background, cached, throttled, and resumable. Choose a **flagship set of about 12 laws** to guarantee the full three-layer view: AI Act, DMA, DSA, Data Act, CSDDD, Omnibus I, NRL, EUDR, CBAM, Euro 7, CO2 cars 2023 and 2025, plus the GDPR practice set. Every other procedure gets the Parltrack amendment layer.

Suggested roles:
- A: data and downloads, resolver.
- B: edge scoring, rarity, tiers, self-audit.
- C: frontend graph and evidence card, any-law flow.
- D, or B after 16:00: insights A–C and the report.

**15:00 checkpoint.** If HYS ingestion is not working at scale:
- Cut to the flagship set.
- Keep the amendment layer for all of 2019–2026.
- Drop multilingual scoring; badge it.
- Drop the ML forecast and keep the rule-based "asks already in Council plus EP text" heuristic, with past hit rate.
- Drop insights F–H.

**17:00 checkpoint.** Freeze features.
- Drop coalitions UI, says-vs-asks, and the reworded tier (or keep it hidden and labelled).
- Must work:
  - the resolver and precomputed any-law view;
  - evidence cards with rarity and dates;
  - five answers;
  - coverage banner.
- One person writes the report full time from now on.
- Run the self-audit of 20 edges per person and set thresholds from it.

**18:30 checkpoint.** Code freeze. Only fixes for demo-breaking bugs.
- Warm all caches.
- Check offline mode and the hotspot.
- Record the backup screen capture.
- Make the repo public with the licences, README and provenance.
- Tag the release.
- Rehearse the 5-minute script twice with a timer, plus one run where a teammate plays the jury and names an obscure law.

**Live failure modes and their mitigations.**

| Failure | Mitigation |
|---|---|
| Random edge looks like boilerplate | Rarity number on every card; top tier only by default |
| Unknown law name | Fuzzy resolver plus procedure-reference search |
| Law without consultation or amendments | Layer badges and honest empty state |
| Non-English paper | "Not analysed (DE)" count |
| Slow network | Everything precomputed and local |
| Jury asks "is this causal?" | "No. It is wording evidence plus timing; see limitations" |
| Defamation risk on named MEPs | Rates, not counts; "matching text", not "copied" |
