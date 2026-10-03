# Influence Atlas: data access research

Researched on Saturday 3 October 2026, between about 10:40 and 11:10 CEST, from the team laptop (EU IP address).

Status tags:

- `verified`: I made the request today and saw the response. The observed shape is quoted.
- `reported`: taken from documentation or search results; not tested.
- `blocked`: I made the request and it was refused.
- `unknown`: not established.

All requests were small, with one accidental exception: the Transparency Register export ignored the HTTP range header, so the full 117 MB file landed in the scratchpad. Nothing was written into the repository.

---

## 1. Have Your Say (HYS), the Commission's "better regulation" API: `verified`

**What it gives.** For each initiative it gives the stages ("publications"): roadmap or inception impact assessment, public consultation (OPC), and the adopted proposal. For each publication it gives every feedback submission with:

- organisation name
- actor type
- country
- size
- Transparency Register ID
- the submitted text
- the attached PDF or DOCX files

**Endpoints (all verified, JSON, no authentication):**

| Purpose | Request | Observed |
|---|---|---|
| Search or list initiatives | `GET https://ec.europa.eu/info/law/better-regulation/brpapi/searchInitiatives?text=<words>&page=0&size=<n>&language=EN` | `{"initiativeResultDtoPage":{"content":[{id, reference, shortTitle, foreseenActType, topics, currentStatuses, ...}], "totalElements":4128, "totalPages":...}}`. Without `text` it lists all **4,128** initiatives. `text=COM(2021)206` returned `general_error`, so you cannot search by COM number. |
| One initiative with its publications | `GET https://ec.europa.eu/info/law/better-regulation/brpapi/groupInitiatives/{initiativeId}?language=EN` | Keys include `id, reference, shortTitle, dg, topics, policyAreas, foreseenActType, stage, publications[]`. Each publication has `id, type (IMPACT_ASSESS_INCEP / OPC_LAUNCHED / PROP_REG / PROP_DIR ...), reference, totalFeedback, adoptionDate, attachments[]`. |
| Feedback for one publication (paged) | `GET https://ec.europa.eu/info/law/better-regulation/api/allFeedback?publicationId={pubId}&page={0..}&size=100` | Spring page: `{content:[...], totalElements, totalPages, last, number, size}`. `size=100` works. |
| Download an attachment | `GET https://ec.europa.eu/info/law/better-regulation/api/download/{documentId}` | `200 application/pdf`, `Content-Disposition: attachment; filename=090166e5e0ab9c0c.pdf`. The rendered file is a PDF even when the upload was a DOCX (the record carries `ersFileName` ending in `.pdf`, and `pdfSize`). |

**Feedback record fields (verified):**

- `id, referenceInitiative ("COM(2021)206"), dateFeedback, feedback (text), language, userType, country, companySize, organization, trNumber, attachments[{id, fileName, ersFileName, documentId, size, pdfSize}], publicationId, scope, governanceLevel, status`
- `trNumber` is **omitted or empty** when the respondent gave none.
- `userType` values seen: `COMPANY`, `NGO`, `BUSINESS_ASSOCIATION`, `OTHER`, `ACADEMIC_RESEARCH_INSTITTUTION` (sic), `TRADE_UNION`, `EU_CITIZEN`.
- `country` is an ISO-3 code (for example `BEL`).

**Measured on the AI Act proposal feedback (publication 14488):**

- 304 submissions; 187 carry a Register ID; 259 have attachments.
- Example record: `CLAIRE … trNumber 205170133342-09 NGO BEL`.
- Organisations include IBM, Facebook Ireland, DIGITALEUROPE, Siemens Healthineers, LinkedIn, Philips, the U.S. Chamber of Commerce and techUK.

**Linking HYS to a procedure number such as 2021/0106(COD).** HYS has no field for the procedure number. The join key is the COM reference:

1. The publication of type `PROP_REG` or `PROP_DIR` has `reference: "COM(2021)206"`, and every feedback record repeats it as `referenceInitiative`.
2. CELLAR maps the procedure to the proposal CELEX `52021PC0206` (see section 7). Convert with `5YYYYPCNNNN ↔ COM(YYYY)NNN`, dropping zero padding.
3. Parltrack dossier events also list the COM document.
4. Because HYS cannot be searched by COM number, build the index once: crawl all 4,128 `groupInitiatives/{id}`, roughly 4k small JSON requests, and map `COM reference → initiative id → publication ids`. The roadmap and OPC publications of the same initiative then come for free.

**Blockers and caveats:**

- **Public consultation questionnaire (OPC) responses are inconsistent.**
  - AI White Paper OPC 25429 (1,216 responses) returns `bad_request` from `allFeedback`. Those responses are not reachable through this API; the questionnaire was probably hosted on EUSurvey, which I did not test.
  - The DSA OPC 13127 (2,863 responses) **does** return records through `allFeedback`.
- Some OPCs are campaign-inflated: the sustainable corporate governance OPC shows `totalFeedback 473461`.
- Licence: Commission reuse policy (Decision 2011/833/EU, CC BY 4.0 equivalent). `reported`.
- Coverage: every Commission initiative since about 2016, so 2019+ is complete.

---

## 2. EU Transparency Register and LobbyFacts

### Transparency Register: `verified`

**Current full export:**

- `https://transparency-register.europa.eu/odplastorganisationxml_en`
- It redirects with 301 to `https://ec.europa.eu/transparencyregister/public/files/ODP/download/XML/latest`.
- Observed: `200`, `Content-Disposition: attachment; filename="ODP_02-10-2026.xml"`, `Content-Length: 116763563` (117 MB). It does **not** honour range requests.
- The header shows `<exportDate>2026-10-02T20:00:00</exportDate><numberOfIR>17897</numberOfIR>`, so the file is refreshed daily.

**Fields per `<interestRepresentative>` (verified):**

- `identificationCode` (for example `880143435725-46`), `registrationDate`, `lastUpdateDate`, `name/originalName`, `acronym`, `entityForm`, `webSiteURL`
- `registrationCategory` (for example "Trade unions and professional associations"), `headOffice/country`, `EUOffice`, `goals`, `levelsOfInterest`
- `EULegislativeProposals`: free text listing the files the organisation follows. This is useful for the ask graph.
- `communicationActivities`, `interOrUnofficalGroupings`
- `members` (people and FTE), `EPAccreditedNumber`, `interests/interest/name` (policy areas)
- `structure/isMemberOf`, `structure/organisationMembers` (association membership)
- `financialData/closedYear/{startDate,endDate,costs,totalBudget,totalAnnualRevenue,grants,clients,intermediaries,contributions,fundingSources}`, `financialData/currentYear/...`

The export contains **no meetings**.

**Historical snapshots:**

- data.europa.eu dataset `transparency-register` lists dated snapshots: XLS, XML and XLSX for 2016, 2017, 2018, 2019, 2021, 2024 and 2025, usually January. Example: `https://data.europa.eu/euodp/en/data/storage/f/2024-05-14T111116/Organisations%20in%20Transparency%20Register-2024-JAN.xml`. `verified` (listed by the data.europa.eu search API).
- Dataset page: https://data.europa.eu/data/datasets/transparency-register

**Join key:** `identificationCode` equals HYS `trNumber`, equals Integrity Watch `OrgId` and `Id`, equals the Commission meetings column "Transparency register ID", equals the LobbyFacts `rid`.

### LobbyFacts.eu (Corporate Europe Observatory and LobbyControl): `verified`

- Per-organisation register history since 2012:
  - `https://www.lobbyfacts.eu/csv_export/{TR-ID}` gives `application/csv`.
  - For Meta `28666427835-74`: **39 rows, one per register snapshot**.
  - Columns include `identification_code, original_name, state_date, registration_date, min, max, calculated_cost, main_category, sub_category, members_fte, activity_eu_legislative, ...`.
- Per-organisation Commission meetings since 2014:
  - `https://www.lobbyfacts.eu/csv_export_meetings/{TR-ID}`
  - Columns: `Date, Subject, Location, Cabinet, DG name/Portfolio, Attending from Commission, Other lobbyists`. 317 rows for Meta.
- Datacards: `https://www.lobbyfacts.eu/datacard/{slug}?rid={TR-ID}`
- I found no bulk export or API. Pulling LobbyFacts data means one request per organisation, which is fine for a few hundred actors.
- Licence: the code is AGPL-3.0 (stated on the about page). The data licence is not stated on the about page, so treat it as `unknown`; the underlying data is Commission data.
- Blocker: requests sent with curl's default user agent were not tested. All my requests used `-A 'Mozilla/5.0'`.

---

## 3. Meetings

### Commission (Commissioners, Cabinets): official XLSX, `verified`

- Dataset: https://data.europa.eu/data/datasets/european-commission-meetings-with-interest-representatives
- Files (`200`, XLSX):
  - `https://ec.europa.eu/transparency-initiative/meetings/data/meetings/dataxlsx?name=meetingscommissionrepresentatives1924` (von der Leyen I, 2019–24, 1.2 MB)
  - `...?name=meetingscommissionrepresentatives2429` (von der Leyen II, 0.9 MB)
  - `...?name=meetingscommissionrepresentatives1419` (Juncker)
- Columns (verified on 2429, "File generated on: 2026-10-03"): `Name of cabinet, Name of EC representative, Title of EC representative, Date of meeting, Location, Name of interest representative, Transparency register ID, Subject of the meeting`.
- The 2429 file has 11,527 rows (2024-11-21 to 2026-10-02); 11,524 carry a Register ID.
- **Only Commissioners and Cabinets.** The file has a second sheet holding the SQL `select * from V_MEETING_DGS`, but it contains no Director-General rows. DG-level meetings are `unknown`; LobbyFacts' meetings CSV has a "DG name/Portfolio" column and may include them.
- **Subject is short free text** (for example "PFAS dossier"). There is no procedure number, so linking a meeting to a law means matching on the subject text plus the date window.

### Integrity Watch EU (Transparency International EU): `verified`

- The web app loads JSON and CSV that are refreshed nightly; the last timestamp seen was `20261003_010004`.
- Commission meetings:
  - Base URL: `https://integritywatch.eu/autoupdate_data_eu/lobbyists_ecmeetings/latest/`
  - Files: `ecmeetings_vonderleyen1.json` (26.5 MB), `ecmeetings_vonderleyen2.json` (52 MB), `ecmeetings_juncker.json`
  - Fields: `{Cat, Cat2, Host[], Org, OrgId (=TR ID), cabinet, date, location, portfolio[], subject, type}`
- Organisations:
  - `.../organizations_new.csv` (7 MB)
  - Columns: `Id, RegDate, Cat, Cat2, Name, Country, People, FTE, Accred, FoI, Costs, Meetings, MeetingsNumVonderleyen2, MeetingsNumVonderleyen1, MepMeetingsNum, MeetingsNumJuncker`
  - This gives cost and meeting counts per Register ID in one file.
- **MEP meetings, 10th term (2024–):**
  - `https://integritywatch.eu/autoupdate_data_eu/mepmeetings/latest/mepmeetings.json` (55 MB, last modified 2026-09-21)
  - Fields: `{committees[], country, date "DD-MM-YYYY", dossier, epid, group, lobbyists, lobbyistsArray[], location, mep, role, title}`
  - `dossier` is often empty.
  - The companion file `mepmeetings_lobbysts_tr_match.json` (2.4 MB) maps lobbyist names to Register IDs.
- **MEP meetings, 9th term (2019–24):** `https://www.integritywatch.eu/data/mepmeetings/legislature_9/mepmeetings.json` (32 MB, `200`).
- Backups index: `.../backups.json` lists weekly snapshots.
- Licence: `unknown` (not stated). Cite Transparency International EU.

### European Parliament declared MEP meetings: `reported`

- Since 2019, MEPs must publish meetings with interest representatives on their EP profile pages (the "Meetings" tab).
- The EP API v2 `meps-declarations` endpoint (verified `200`) returns **financial and other declarations as PDFs** (for example `DCI-…_en.pdf`), not meetings.
- For meetings, use the Integrity Watch scrape above.

### Council: `unknown`

- There is no structured feed of Council or Permanent Representation lobby meetings.
- Council documents are linked from Parltrack dossier events (`register.consilium.europa.eu` URLs, seen in the schema). Skip for today.

---

## 4. Parltrack: `verified`

- Dumps page: https://parltrack.org/dumps. Licence: **ODbL v1.0** for data, AGPL-3.0 for code (stated on the page).
- Format: zstd-compressed JSON with one record per line. The first line starts with `[`, later lines with `,`, and the last line is `]`.

| Dump | URL | Size | Last updated |
|---|---|---|---|
| Dossiers (OEIL mirror) | https://parltrack.org/dumps/ep_dossiers.json.zst | 52.7 MiB (`Content-Length: 55253515`) | 2026-07-24 |
| MEPs | `/dumps/ep_meps.json.zst` | 8.9 MiB | 2026-07-24 |
| MEP activities | `/dumps/ep_mep_activities.json.zst` | 47.4 MiB | 2026-07-24 |
| Plenary amendments | `/dumps/ep_plenary_amendments.json.zst` | 6.7 MiB | 2026-07-24 |
| Committee amendments | `/dumps/ep_amendments.json.zst` | 114.4 MiB | **2026-02-03** |
| Plenary votes | `/dumps/ep_votes.json.zst` | 10.7 MiB | 2026-03-28 |
| Committee votes | `/dumps/ep_com_votes.json.zst` | 28 KiB | 2026-07-24 |
| Committee agendas | `/dumps/ep_comagendas.json.zst` | 1.2 MiB | 2026-02-28 |

- Dated archives live at `/dumps/arch/<name>-YYYY-MM-DD.json.zst`. Schemas live at `/schemas/<name>`.
- **Blocker:** the per-dossier JSON route `https://parltrack.org/dossier/2021/0106(COD)?format=json` returns `{"STOP":"scraping!"}`. Use the dumps only.
- Freshness: all dumps stopped on 2026-07-24, and committee amendments on 2026-02-03. Laws negotiated after those dates are missing from Parltrack; use the EP API instead.

**Dossier fields that matter**, from the schema at https://parltrack.org/schemas/ep_dossiers. This is `verified` by reading the schema, not by downloading the dump:

- `procedure.reference` ("2014/0802(NLE)"), `procedure.title`, `procedure.stage_reached` ("Procedure completed")
- `procedure.subject`: **OEIL subject codes**, for example `8.40.05`, `3.70.02`. These give the topic classification.
- `procedure.final {title: "Decision 2014/108", url: "https://eur-lex.europa.eu/...numdoc=32014D0108"}`. The **CELEX number sits in the `numdoc` URL parameter.** The field is present in 36.6% of dossiers, essentially the completed ones.
- `procedure.dossier_of_the_committee`, `procedure.legal_basis`, `procedure.geographical_area`
- `committees[] {type: "Responsible Committee", committee, rapporteur ...}`
- `events[] {date, type ("Legislative proposal published"), body, docs[] {url, title e.g. COM(2019)0308}}`
- `docs[]`

**Joins:**

- amendment `reference` → dossier `procedure.reference` → `procedure.final` CELEX
- amendment `meps[]` (EP ids) → `ep_meps`

**Amendment adoption status.** The committee amendment records have no outcome field. Observed fields: `authors, changes, committee, date, id, location, meps, meta, new, old, orig_lang, peid, reference, seq, src`. Adoption has to be inferred, in one of two ways:

- (a) text-match the amendment `new` text against the committee report (A9-xxxx), the EP first-reading position (TA-9-…) and the final act. This is the War of Words approach.
- (b) for plenary amendments, use HowTheyVote vote results (section 6).

**Local counts of committee amendments** (`zstdcat … | grep -c`, measured today):

| Procedure | Law | Amendments |
|---|---|---|
| 2021/0106(COD) | AI Act | 4,852 |
| 2020/0361(COD) | DSA | 5,901 |
| 2022/0051(COD) | CSDDD | 5,934 |
| 2020/0374(COD) | DMA | 3,261 |
| 2021/0218(COD) | — | 2,994 |
| 2023/0079(COD) | — | 3,096 |
| 2021/0211(COD) | — | 2,559 |
| 2022/0140(COD) | EHDS | 2,458 |

---

## 5. European Parliament Open Data Portal API v2: `verified`

- Base URL: `https://data.europarl.europa.eu/api/v2/`. Use `?format=application%2Fld%2Bjson&offset=0&limit=N`. No authentication.
- Endpoints answered `200`: `procedures`, `adopted-texts`, `plenary-documents`, `committee-documents`, `meetings`, `meps`, `meps-declarations`.
- `GET /api/v2/procedures/2021-0106` (23.5 KB) returned:
  - `label "2021/0106(COD)"`, multilingual `process_title`, `current_stage`
  - `created_a_realization_of[]`: 17 document ids such as `eli/dl/doc/A-9-2023-0188`, `TA-9-2023-0236`, `ENVI-AD-…`, `ITRE-PA-…`, `CJ40-PR-731563`
  - `consists_of[]`: 26 events with `had_activity_type`, for example `COMMITTEE_ADOPTING_REPORT`, `PLENARY_VOTE`, `PLENARY_AMEND`, `SIGNATURE`, `PUBLICATION_OFFICIAL_JOURNAL 2024-07-12`
- **The response has no CELEX or Official Journal link and no committee amendment (`-AM-`) documents.** Use CELLAR for the final act and Parltrack for committee amendments.
- `adopted-texts` items carry `adopts` (the report id), `is_about` (EuroVoc URIs) and multilingual manifestations. The full text of the EP first-reading position is reachable this way.
- Plenary amendment PDFs follow the pattern `https://data.europarl.europa.eu/distribution/reds_iPlRp_Amd/A-9-2023-0048-AM-189-189/A-9-2023-0048-AM-189-189_en.pdf` (seen in HowTheyVote's `amendment_urls`).
- Coverage: 2019 onwards is good. This API is the fallback for anything Parltrack lacks after July 2026.

---

## 6. HowTheyVote.eu: `verified`

- Weekly CSV export on GitHub, latest release `2026-10-03`.
- Stable link pattern: `https://github.com/HowTheyVote/data/releases/latest/download/<file>.csv.gz`. The full archive is `export.zip` (70 MB).
- Files:
  - `votes.csv.gz` (784 KB)
  - `member_votes.csv.gz` (68 MB)
  - `members`, `groups`, `group_memberships`
  - `amendment_urls`, `amendment_authors_votes`
  - `oeil_subjects`, `oeil_subject_votes`, `eurovoc_concepts`, `eurovoc_concept_votes`
  - `responsible_committee_votes`, `committees`, `countries`, `geo_areas`, `geo_area_votes`
- `votes.csv` columns: `id, timestamp, display_title, reference, description, amendment_subject, amendment_number, is_main, procedure_reference, procedure_title, procedure_type, procedure_stage, count_for, count_against, count_abstention, count_did_not_vote, result, texts_adopted_reference`.
- Size: 25,204 roll-call votes from 2019-07-15 to 2026-09-17; 22,742 have `is_main=False`, meaning amendment or split votes.
- **Amendment-level plenary votes: yes.** The AI Act has 30 roll-call votes, for example `"Article 2, § 3 - Am 792" for 140 / against 471` and `"Amendements de la commission compétente - vote séparé - Am 227"`. `amendment_urls` maps a vote id to the EP amendment PDF, and `amendment_authors_votes` gives `author_type` (COMMITTEE, group) with `group_code` and `committee_code`.
- Limitation: roll-call votes only, plenary only. No committee votes and no amendments adopted by show of hands.
- Licence: **ODbL** for the data, Database Contents License for contents (about page).
- Join key: `procedure_reference` ("2021/0106(COD)").

---

## 7. EUR-Lex and the Publications Office CELLAR: `verified`

**Procedure number → final act CELEX and proposal CELEX, in one SPARQL call.** Endpoint: `https://publications.europa.eu/webapi/rdf/sparql`, GET with `query=` and `Accept: application/sparql-results+json`.

```sparql
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?proc ?final ?prop WHERE {
  VALUES ?proc { <http://publications.europa.eu/resource/procedure/2021_106> }
  ?d owl:sameAs ?proc .
  OPTIONAL { ?d cdm:dossier_produces_resource_legal ?w . ?w cdm:resource_legal_id_celex ?final . }
  OPTIONAL { ?d cdm:dossier_initiated_by_act_preparatory ?p . ?p cdm:resource_legal_id_celex ?prop . }
}
```

Observed results:

- `2021_106 → final 32024R1689, prop 52021PC0206` (AI Act)
- `2020_361 → 32022R2065, 52020PC0825` (DSA)
- `2022_51 → 32024L1760, 52022PC0071` (CSDDD)
- `2022_66 → 32024L1385, 52022PC0105` (violence against women directive)

Notes:

- The procedure URI is `procedure/YYYY_N`: year, underscore, number without zero padding. The procedure type is not part of the URI.
- The dossier also exposes `dossier_contains_work`, which lists every document of the procedure (amended proposals, opinions and so on).
- The work also carries `resource_legal_eli` (for example `http://data.europa.eu/eli/reg/2024/1689/oj`).

**Text by CELEX, through content negotiation:**

- Request: `curl -L -H 'Accept: application/xhtml+xml' -H 'Accept-Language: eng' http://publications.europa.eu/resource/celex/32024R1689`
- Final act: `200 application/xhtml+xml`, 1.26 MB, resolved to `.../cellar/dc8116a1-....0006.03/DOC_1`.
- Commission proposal `52021PC0206`: returns **`300 Multiple Choices`**, an HTML list of streams (`1_EN_ACT_part1_v7.html`, `1_EN_annexe_proposition_part1_v7.html`, …). Follow the `DOC_1` link (the act) and `DOC_3` (the annex). `DOC_1` returned `200`, 589 KB of XHTML containing "Proposal for a …".

**Blocker: EUR-Lex website scraping.** `https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1689` returned **`202` with an empty body**, a bot-challenge page. Always use CELLAR, never eur-lex.europa.eu, from scripts.

Licence: Commission reuse policy (CC BY 4.0). `reported`.

---

## 8. OEIL (Legislative Observatory)

- **Machine-readable route:** OEIL has no public API that I tested. Two mirrors work:
  - **Parltrack `ep_dossiers`**: each record's `meta.source` is the OEIL `ficheprocedure.do?reference=…` URL. `verified` from the schema.
  - **EP API v2 `/procedures/{YYYY-NNNN}`**: `verified` above.
- **Subject codes for topics:**
  - Parltrack `procedure.subject` holds OEIL codes with labels (for example `3.70.02 Atmospheric pollution`, `8.40.16 Relations with interest representatives`). `verified` in the schema.
  - HowTheyVote ships `oeil_subjects.csv.gz` and `oeil_subject_votes.csv.gz`. `verified`, listed in the release.
  - EP API adopted texts carry EuroVoc `is_about`.
  - HYS initiatives carry their own `topics` (for example `DIGITAL`) and `policyAreas`. Use OEIL codes as the canonical topic and map the HYS topics onto them.

---

## 9. GDELT DOC 2.0 API: `blocked` (rate-limited)

- Endpoint: `https://api.gdeltproject.org/api/v2/doc/doc?query=<q>&mode=ArtList&maxrecords=<≤250>&format=json&timespan=<e.g. 12months>`
- All three attempts, spaced 6–10 s apart, returned **`HTTP 429`**: "Please limit requests to one every 5 seconds … All high-traffic users should switch to our ngrams dataset". The IP may already be throttled, perhaps shared with other teams.
- `reported` limits: DOC 2.0 searches only about the **last 3 months** of coverage (`timespan`, or `startdatetime`/`enddatetime`). It returns article URLs, titles, dates and source countries, but no full text.
- Verdict: unreliable for a live demo and shallow for 2019+. If you use it, cache results and add a delay of at least 6 s between calls. A better press-coverage proxy is the organisations' own press releases.

---

## 10. US Lobbying Disclosure Act (LDA) API: `blocked`

- `https://lda.senate.gov/api/v1/` now **redirects with 301 to `https://lda.gov/api/v1/`**.
- Every request, including one with a descriptive user agent, returned **`403 Access Denied` (Akamai)**, so the API cannot be reached from this network. The cause may be the geography of the IP or a new API-key requirement; it is not established.
- `reported`, from earlier documentation:
  - Endpoints: `/filings/?client_name=&filing_year=&filing_period=`, `/registrants/`, `/clients/`, `/lobbyists/`
  - Fields: `lobbying_activities[].general_issue_code` (for example `CPI`, `SCI`), free-text `description`, `government_entities`, `income`, `expenses`
  - Anonymous access was rate-limited and an API key could be requested.
- Meta, Google and Microsoft file quarterly, so they would match by name, but no shared identifier exists with the EU Register.
- Verdict: drop it for today unless someone on another network can test it.

---

## 11. Existing public datasets usable as labels (2019+ coverage is thin)

| Dataset | URL | What is labelled | Period | Status |
|---|---|---|---|---|
| **War of Words II** (Kristof, Suresh, Grossglauser, Thiran, WWW 2021) | https://zenodo.org/records/4709248 (CC BY 4.0) | About 240k EP committee amendments ("edits") with an **`accepted` label** (adopted into the committee report or not), plus conflicts between edits and rapporteur/MEP features. Files: `war-of-words-2-ep7.txt` (449 MB), `war-of-words-2-ep8.txt` (607 MB), text embeddings and split indices. | EP7 and EP8, **2009–2019; not 2019+** | `verified` (Zenodo API metadata) |
| "Discovering Lobby-Parliamentarian Alignments through NLP" (Suresh et al., NAACL 2024; arXiv 2309.11381) | https://arxiv.org/abs/2309.11381 | Lobby position papers and MEP speeches with semantic similarity and entailment. It is validated against MEP–lobby **retweets and declared MEP meetings**. It contains **no amendment-copy labels**. I found no dataset URL. | EP9 (2019+) | `reported` |
| LobbyPlag (already local) | — | Lobby → amendment copies | GDPR 2012–13 | in hand |
| Corporate Europe Observatory, AI Act reports (for example "Big Tech's last-minute blitz…") | https://corporateeurope.org/en/node/2036 | Narrative. Meeting statistics: 66% of 2023 MEP meetings on the AI Act were with corporate interests, and 86% of Commission high-level meetings. Also lobby positions compared with outcomes on foundation models. **Not a labelled copy dataset.** | 2021–24 | `reported` (search snippet) |
| CEO and LobbyControl, DSA/DMA | https://corporateeurope.org/en/2022/01/corporate-lobbying-undermined-eus-push-ban-surveillance-ads | Meeting counts: 613 MEP lobby encounters on the DSA, with Google 23, Facebook 16, Amazon 15 and Microsoft 12. Positions compared with outcomes on surveillance ads. No amendment-level labels. | 2020–22 | `reported` |
| InfluenceMap, EU policy trackers | https://europe.influencemap.org , methodology https://www.climateaction100.org/wp-content/uploads/2023/10/2023-InfluenceMap-Methodology.pdf | Per-company and per-association **position scores** (0–100, supportive to obstructive) on specific EU climate files (Fit for 55 and others), backed by evidence items since December 2019. Score downloads exist on the site; their terms are `unknown`. This is useful for checking the gap between what an actor says and what it asks, **not** for amendment copies. | 2019+ | `reported` |
| Follow the Money and Politico, copied amendments for AI Act, DMA, DSA, CSDDD | — | I found no specific investigation with a published list of copied amendments for these laws in the time available. | — | `unknown` |

**Practical takeaway.**

- For 2019+, there is **no public gold set of lobby → amendment copies**.
- The best substitutes, all reproducible:
  - (a) **LobbyPlag GDPR** for copy detection, pre-2019.
  - (b) **War of Words** `accepted` labels to train or validate a model of whether an amendment is adopted, pre-2019.
  - (c) **HowTheyVote** amendment results as 2019+ labels of whether an amendment was adopted in plenary.
  - (d) Weak labels: a meeting between the organisation and the MEP who tabled the amendment, from the Integrity Watch MEP meetings with `lobbyists` and `mep`, within ±60 days.

---

## 12. Candidate laws for an end-to-end vertical slice (all verified today)

| Law | Procedure | Final act (CELLAR) | Proposal | HYS initiative and feedback counts | Parltrack committee amendments (local) |
|---|---|---|---|---|---|
| **AI Act** | 2021/0106(COD) | 32024R1689 | 52021PC0206 = COM(2021)206 | 12527: inception IA pub 13340 (133), White Paper OPC pub 25429 (1,216; **not via API**), proposal pub 14488 (**304**, 187 with Register ID, 259 with attachments) | 4,852 |
| **Digital Services Act** | 2020/0361(COD) | 32022R2065 | 52020PC0825 = COM(2020)825 | 12417: inception IA pub 13125 (110), OPC pub 13127 (**2,863**, reachable via `allFeedback`), proposal pub 13971 (138) | 5,901 |
| **CSDDD** (corporate sustainability due diligence) | 2022/0051(COD) | 32024L1760 | 52022PC0071 = COM(2022)71 | 12548: inception IA pub 13393 (114), OPC pub 13672 (473,461; campaign-dominated), proposal pub 15775 (**288**) | 5,934 |

The DMA (2020/0374(COD), HYS 12418, proposal COM(2020)842 with 90 feedbacks, 3,261 amendments) is a fourth option. It shares the DSA's OPC (pub 25545, 2,863).

**Recommendation:** start with the **AI Act**. It has the richest proposal-stage feedback with Register IDs, strong press interest, and HowTheyVote amendment votes (30). The **DSA** is second: its OPC is reachable through the API, which gives many early asks.

---

## 13. Recommended join plan, from a procedure number

Input: `2021/0106(COD)`.

### (c) Final act and proposal: CELLAR

1. Normalise the procedure number to `procedure/2021_106`.
2. Run the SPARQL query in section 7 to get `final = 32024R1689` and `prop = 52021PC0206`.
3. Fetch the texts with `GET http://publications.europa.eu/resource/celex/{CELEX}` and the headers `Accept: application/xhtml+xml` and `Accept-Language: eng`.
4. For the proposal, follow the `300` list: `DOC_1` is the act and the annex is the stream named `annex…`.
5. Cross-check against Parltrack `procedure.final.url` (`numdoc=`).
6. For a law still under negotiation, `final` is empty. Use the proposal plus the EP position (EP API `adopted-texts`, `TA-…`) as the "current text", and predict instead.

### (a) Consultation submissions: HYS

1. Convert `52021PC0206` to `COM(2021)206`.
2. Look up the COM number in a pre-built index (crawl `brpapi/groupInitiatives/{id}` for all 4,128 initiatives once and cache it). This gives initiative `12527` and publications `13340`, `25429` and `14488`.
3. For each publication, page through `api/allFeedback?publicationId=…&page=k&size=100` until `last=true`.
4. Download each `attachments[].documentId` with `api/download/{documentId}` (PDF).
5. Fallback, when the index is not built: `searchInitiatives?text=<words from the law title>`, keeping candidates whose `PROP_*` publication reference equals the COM number.

### (b) Committee amendments: Parltrack, then the EP API

1. Filter `ep_amendments` on `reference == "2021/0106(COD)"`.
2. Join `meps[]` to `ep_meps` for name, group and country.
3. Join `committee` to the dossier's `committees[]`, which tells whether the committee was responsible or gave an opinion.
4. Infer adoption by aligning the amendment `new` text with three texts: the committee report (from `ep_dossiers` events and docs, or EP API `A-9-2023-0188`), the EP position (`TA-9-2023-0236`) and the final act from (c).
5. Use HowTheyVote `votes.csv` (`procedure_reference`, `amendment_number`, `result`) as hard labels for plenary amendments.
6. For amendments after February 2026, Parltrack is stale. Use EP API committee documents instead (not tested at amendment level).

### (d) Actors: Register IDs, budgets and meetings

1. **Register ID** comes from the HYS `trNumber`. When it is missing, match the organisation name against the register export `name/originalName` and `acronym` after normalising.
2. **Budget, category and members** come from the register XML `financialData/closedYear/costs` and `totalBudget`, plus `registrationCategory`.
3. **History back to 2012** comes from LobbyFacts `csv_export/{TR-ID}`, one call per actor.
4. **Commission meetings** come from the official XLSX (`Transparency register ID` column) or from Integrity Watch `ecmeetings_vonderleyen{1,2}.json` (`OrgId`). Filter to the law by date window (proposal date to adoption) and by subject keywords. No procedure field exists.
5. **MEP meetings** come from Integrity Watch `mepmeetings.json`, legislatures 9 and 10. Match lobbyists to Register IDs with `mepmeetings_lobbysts_tr_match.json`. Use `dossier` where present, otherwise `title` keywords and the date window. Join `epid` to the Parltrack `meps[]` of the amendment author: a meeting between the author and the lobby before the tabling date is strong corroboration for a copy link.
6. **Shortcut:** Integrity Watch `organizations_new.csv` already gives `Costs`, `Meetings`, `MepMeetingsNum` and `FTE` per Register ID in one 7 MB file.

### Topic and year for rankings

- Topic: Parltrack `procedure.subject` (OEIL codes) or HowTheyVote `oeil_subjects`.
- Year: HYS `dateFeedback`, amendment `date` and final act date.

### Skip or deprioritise today

- GDELT: rate-limited.
- US LDA: 403 from this network.
- Council meetings: no feed.
- EUR-Lex website: bot wall. Use CELLAR instead.
