# Research: The Reversa Challenges at the Madrid Open, From First Principles

**Date:** 2026-10-02 (last updated 2026-10-02)

**Author:** Claude (Claude Code), for Lensa Billion’s team; tracked as bead `chamber-gyjt`

**Status:** Complete

## Overview

On 1–2 October 2026 Reversa replaced the brief for its Madrid Open track.
The original parliamentary-transcripts track stays open but is judged by a jury alone.
Reversa recommends three new challenges, each scored against answers the teams never
see: **01 Law × Markets**, **02 Bill-to-Law Predictor** and **03 Influence Graph**.
Teams must reply by Friday 2 October with their team and their pick; the event runs on
Saturday 3 October, 09:00–21:00, at Mad Tech Campus.

This brief answers one decision (which option to pick) and prepares the team to execute
it. Each option is explained from the ground up: what the problem is, why it matters to
Reversa, how the underlying law or market works, what public data exists (checked live
on 2 October), what has been done before, how the scoring can be gamed or failed, and
how to approach it. Where this research could measure something itself, it did, and
the scripts are in [evidence/](reversa-2026-10/evidence/README.md).

Two companion files are machine-readable softschema catalogs, validated against their
schemas:

- [data-sources.yaml](reversa-2026-10/data-sources.yaml): 26 public sources, each marked
  `verified` (fetched and inspected) or `reported` (described elsewhere, not fetched)
- [prior-work.yaml](reversa-2026-10/prior-work.yaml): 31 papers, datasets, tools and
  articles, each marked `read` or `cited`

The source brief is the organizers’ 16-page PDF,
[madrid-open-reversa-challenges.pdf](../brief/madrid-open-reversa-challenges.pdf)
(shared by email), together with organizer Tomás Burgaleta’s two
emails.

## Questions to Answer

1. How is the event scored, and what does that imply for the choice?
2. How are laws made in Spain and the EU, at the level needed to model them?
3. For each option: what exactly is being predicted, which public data exists, what
   prior work exists, what are the traps, and what approach would score well?
4. What have Reversa or anyone else already built or published on these problems?
5. Which option gives this team the best chance of winning, and what should happen
   before and during the day?

## Scope

Included: the open track and all three challenges; Spanish and EU data sources; prior
academic and applied work; scoring mechanics; measured baselines where the data allowed.

Excluded: building the actual submission pipeline; legal advice; anything requiring paid
data. Advance-preparation rules are unconfirmed (see
[Questions for the Organizers](#questions-for-the-organizers)), so the measurements here
are research, not a prepared dataset.

## Findings

### 1. How the Event Is Scored

| Component | Weight | What it rewards |
| --- | --- | --- |
| Hidden test | 60% | Your CSV against answers you have never seen |
| Difficulty | 20% | Harder problems and bonus layers score more |
| Demo | 20% | Live, on real data, explained to a non-lawyer |

The day: 09:00 kickoff, 09:30–11:00 find and load data, 11:00–19:00 build, **19:00 test
inputs published, 20:00 CSV due**, then five-minute demos until 21:00. The top three
re-run their pipeline live. Teams of three, own tools, public data only. No data is
handed out: “we tell you where to look, not what to download.”

What follows from this:

- **The hour from 19:00 to 20:00 decides 60% of the score.** At 19:00 you receive bare
  inputs (bill IDs, event descriptions, or amendment–submission pairs). Anything that
  cannot turn those inputs into a valid CSV automatically, inside an hour, is worthless.
  Build that path first and improve the model second.
- **The open track is outside this scoring.** It is “judged by the jury” on ambition, use
  of real data and a working live demo. It has no hidden test, so whether it competes for
  the same prize is unclear.
- **Difficulty is partly fixed by the choice.** Reversa rates 01 and 02 at 4/5 and 03 at
  5/5; each challenge has a bonus layer that adds difficulty credit.
- **The judges are the founders.** Reversa’s three founders all hold law degrees, and
  the event is openly part hiring funnel (see
  [the Madrid Open research note](https://github.com/jlevy/thinking/blob/main/docs/project/research/research-2026-09-02-madrid-open-reversa-challenge.md)).
  Reversa’s product includes “Legislative Twins”, which track EU procedures, votes and
  amendments. Challenges 02 and 03 sit directly beside that product.

### 2. Foundations: How Laws Are Made

#### 2.1 Spain

Spain’s parliament, the Cortes Generales, has two chambers. The **Congreso de los
Diputados** (350 deputies) is the one that matters for passing laws; the **Senado** can
delay and amend but not finally block.

**The arithmetic.** 176 deputies is an absolute majority.
Since 2015 no party has come close, so every law needs a coalition of parties. Ordinary
laws need more yes than no votes among those present. **Organic laws** (those touching
fundamental rights, electoral rules and similar areas) need 176 yes votes in a final vote
on the whole text, under Article 81 of the Constitution.

**Who can propose a law.**

| Type code | Name | Who files it |
| --- | --- | --- |
| 121 | Proyecto de ley (government bill) | The Council of Ministers |
| 122 | Proposición de ley de grupos | One or more parliamentary groups |
| 124 | Proposición de ley del Senado | The Senate |
| 125 | Proposición de ley de comunidades autónomas | A regional parliament |
| 120 | Iniciativa legislativa popular | 500,000 citizens’ signatures |

The codes are the first part of every initiative ID (for example `121/000150`) and are
how the Congress website filters bills.

**The path of a bill.**

1. **Filing and qualification.** The bill is registered (filing date) and the **Mesa**,
   the Congress’s governing board, qualifies it, usually within one or two weeks. The
   Mesa also sets deadlines and can extend them.
2. **The government’s say on group bills.** For bills from groups, the government has a
   period to state its view. Under Article 134.6 of the Constitution, any bill that would
   raise spending or cut revenue in the current budget needs the government’s consent
   to proceed, a de facto veto.
3. **Consideration vote (toma en consideración).** The plenary votes on whether to
   debate a group bill at all. Government bills skip this step.
4. **Amendments.** Groups table whole-text amendments (to reject or replace the bill)
   and article-by-article amendments. This is where bills are frozen: the Mesa can
   extend the amendment deadline week after week. In legislature XV it agreed more than
   628 extensions for group bills between November 2023 and January 2025, and only bills
   signed by the governing PSOE group advanced past this phase
   ([Demócrata](https://www.democrata.es/demodata/no-psoe-no-boe-la-mesa-del-congreso-bloquea-en-fase-de-enmiendas-todas-las-proposiciones-de-ley-sin-firma-socialista/)).
   The Constitutional Court upheld deputies’ appeal against 71 unexplained extensions of
   one urgent bill’s deadline
   ([Iberley](https://www.iberley.es/noticias/el-tc-ampara-diputados-prorrogas-reiteradas-enmiendas-36335)).
5. **Committee.** A small working group (ponencia) writes a report; the committee votes
   its opinion (dictamen). Under “full legislative competence” the committee’s vote is
   final and the plenary is skipped.
6. **Plenary vote** (for organic laws, the 176 threshold).
7. **Senate.** Two months (20 days if urgent) to amend or veto. Congress can override a
   veto by absolute majority immediately, or by simple majority after two months.
8. **Publication.** The King signs, and the law takes effect legally once published in
   the **BOE** (Boletín Oficial del Estado). The challenge’s target is BOE publication.

**The graveyard.** A legislature lasts at most four years. When parliament is dissolved,
almost everything still in progress lapses (“caducado”). Early or repeat elections
(2016, 2019 twice, 2023) therefore kill many bills, government bills included.

**Decree-laws.** In urgent cases the government can legislate directly by **Real
Decreto-ley**, which takes effect at once and must be ratified by Congress within 30
days (Article 86). Congress may also decide to process the decree as a bill, so it can be
amended. Those bills carry “procedente del Real Decreto-ley …” in their title. Because
the decree is already law, the government has little reason to push them, and many
lapse.

#### 2.2 The European Union

The **European Union (EU)** is 27 European countries that make some laws together; those
laws then apply in all 27. A well-known example is the **GDPR**, the EU privacy law, which
is why websites ask visitors to accept cookies. Three bodies make EU laws:

- **The European Commission**, the EU’s executive and civil service, writes the first
  draft, called the **proposal**.
- **The European Parliament** has 720 members, called **MEPs** (Members of the European
  Parliament), elected in each country every five years. They are the EU’s equivalent of
  members of a national parliament or of the US Congress: they edit draft laws and vote
  on them.
- **The Council of the EU** is made up of ministers from each national government. It
  also edits and votes.

Parliament and Council must agree on the same final text.

**Lobbying** means organizations trying to shape a law that affects them: companies,
industry associations, campaign groups and unions. It is legal and normal in the EU.
Lobbyists reach a law through two doors: the Commission’s public consultation, and papers
sent directly to MEPs, often containing ready-written edits.

The steps in detail:

1. **Proposal.** The Commission (almost always) proposes. Beforehand it publishes calls
   for evidence and public consultations on the **Have Your Say** portal, where anyone,
   lobbyists included, can submit comments and position papers.
2. **Lobbying is registered.** Organizations that lobby EU institutions register in the
   **Transparency Register**; MEPs publish meetings with lobbyists.
3. **Parliament amends.** A lead committee appoints a **rapporteur** (the MEP in charge
   of the file), who drafts a report. Every MEP can table numbered amendments. Each
   amendment shows the Commission’s text in one column and the proposed change in the
   other. The committee, then the full Parliament (the plenary), vote on them.
4. **Council and trilogues.** Council adopts its own position; Parliament, Council and
   Commission negotiate a compromise in three-way talks called **trilogues**.
5. **Adoption and publication** in the Official Journal; the text is on EUR-Lex.

The challenge’s question is how much of step 3 (and the final law) came from step 1’s
submissions.

### 3. Toolkit: The Ideas Needed to Read the Challenges

Each challenge is scored with standard statistics. Here is what each measure means, from
scratch.

**Probability and calibration.** A prediction such as “p_law = 0.8” claims that, among
many bills given 0.8, about 80% become law. A model is **calibrated** when this holds.
Calibration matters whenever a score uses the probability itself, not just its ranking.

**Brier score.** The average of (prediction − outcome)², where outcome is 1 or 0. Saying
0.9 for a bill that passes costs 0.01; saying 0.9 for one that fails costs 0.81. Lower is
better. Always predicting 0 or 1 is punished heavily when wrong, so honest probabilities
beat confident guesses.

**AUC (area under the ROC curve).** Take a random bill that became law and a random one
that did not. AUC is the chance your model gives the first a higher score. 0.5 is a coin
flip, 1.0 is perfect ranking. AUC ignores calibration; it only checks the ordering. A
yes/no rule that gives every government bill the same score ranks poorly inside each
group, which is why it is beatable on AUC.

**Logistic regression.** A model that adds up weighted features (for example +2.6 for
“government bill”) and squashes the total into a probability between 0 and 1. It is
simple, stable on small data and easy to explain.

**Gradient-boosted trees.** Many small decision trees, each correcting the previous
ones’ errors. Strong on tabular data with interactions; easier to overfit on small data.

**Leakage.** Using information the model would not have had at prediction time. The bill
challenge disqualifies any use of events after the filing date. Leakage makes offline
scores look excellent and real scores collapse.

**Temporal validation.** Train on the past, test on later periods. Here, “leave one
legislature out” trains on all other legislatures and tests on the held-out one, which
mimics predicting bills you have never seen.

**Survival analysis and censoring.** For “when will it pass?”, some bills are still
pending: we know they have taken at least N days but not the final answer. These are
**censored** observations; dropping them biases durations downwards. Bills also end in
competing ways (law, rejection, lapse, withdrawal), which is a **competing-risks**
problem.

**MAE (mean absolute error).** The average size of your miss, here in days. Predicting
the median minimizes MAE for a constant guess.

**Abnormal return.** A share’s price change minus what the whole market did. If the IBEX
35 fell 0.6% and a bank fell 8.6%, the abnormal return is −8.0%: the part the market as
a whole does not explain.

**Prediction intervals and coverage.** An 80% interval should contain the real value 80%
of the time. If it contains it 95% of the time, it is too wide; 50%, too narrow.
**Conformal prediction** calibrates intervals on held-out errors so coverage comes out
right on average
([Angelopoulos and Bates](https://arxiv.org/abs/2107.07511)).

**Monte Carlo simulation.** Draw thousands of random scenarios (passes or not, when, how
strict) from stated probabilities, compute the outcome for each, and read off the 10th,
50th and 90th percentiles (P10/P50/P90).

**Precision, recall and F1.** Precision: of the items you flagged, the share that were
right. Recall: of the items that were right, the share you flagged. F1 combines both.
“Precision in your top 20” means only your 20 highest-scored items are checked.

**Text reuse.** Two texts share wording. **N-grams** are runs of N consecutive words;
shared rare n-grams are strong evidence of copying. **Local alignment**
(Smith-Waterman) finds the best-matching stretch between two texts while allowing small
insertions and deletions, the way DNA sequences are compared. **Embeddings** turn
sentences into vectors so that paraphrases land close together. **Boilerplate** is
standard legal phrasing (“Member States shall ensure that …”) that appears everywhere;
it must be down-weighted, typically by how common a phrase is across a large legal
corpus (inverse document frequency).

### 4. The Open Track: Parliamentary Transcripts

**The problem.** Build anything on what is said and voted in the Spanish Congress. The
brief suggests: a virtual parliament with one agent per group, trained on its speeches
and votes; a detector of what a group says versus how it votes; an early warning that a
coalition is cracking. Judged on ambition, use of real data and a live demo.

**Data (verified).** Congress publishes every roll-call vote with each deputy’s vote from
legislature X (December 2011), interventions, deputies and initiatives
([data-sources.yaml](reversa-2026-10/data-sources.yaml): `congreso-opendata-votaciones`,
`congreso-opendata-intervenciones`). A community clone (`congreso-api`) has 142
legislature-XV sessions in a compact form. ParlaMint-ES provides annotated speeches,
mostly 2015 to mid-2022. HowTheyVote.eu covers the European Parliament.

**Prior work.** Speeches show much wider disagreement inside parties than disciplined
votes do ([Schwarz, Traber and Benoit 2017](https://eprints.lse.ac.uk/62295/)), which is
the academic basis for a say-versus-vote detector. LLM agents role-playing US House
members have predicted roll-call votes with readable reasoning
([Political Actor Agent, AAAI 2025](https://arxiv.org/abs/2412.07144)).

**Measured here: an early-warning signal for the Junts break.** On 27 October 2025 Junts
formally broke its investiture pact with the PSOE. Using the 142 session files, this
research computed how often the majority of each group voted the same way as the
majority of the PSOE group
([coalition-agreement.txt](reversa-2026-10/evidence/coalition-agreement.txt)).

| Month (2025) | Feb | Mar | Apr | May | Jun | Jul | Sep | Oct | Nov |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Junts–PSOE agreement | 70% | 73% | 79% | 67% | 70% | 76% | **57%** | 52% | 58% |
| Votes in month | 61 | 106 | 24 | 54 | 54 | 21 | 56 | 182 | 142 |

Agreement fell by roughly 15 points in September, a month before the formal break, and
stayed low (43–56% in early 2026). This is one case on an incomplete session set, and the
mix of votes changes over time, so it is suggestive rather than proof. It shows the
“coalition is cracking” idea is measurable with public data.

**Assessment.** Attractive for a demo and the closest to this repository’s existing
work, but it forgoes the hidden test that carries 60% of the scoring for the recommended
challenges, and Reversa says its own team has already solved much of it.

### 5. Challenge 01: Law × Markets

#### 5.1 The Problem in Plain Words

When a government announces a law that will cost companies money, their share prices
move. The challenge: measure that move properly, explain why it differs across
companies, and estimate in euros what a pending law could do.

#### 5.2 Why Prices Move: First Principles

A share price is the market’s current estimate of the present value of all the cash a
company will pay its owners in the future. A new tax lowers expected future cash flows,
so the price drops, but only by the part investors did not already expect. Prices move
when *news* arrives, not when a law is published, if publication was certain. This has
three consequences:

1. **Surprise drives the size.** An announcement nobody saw coming moves prices more than
   a vote everyone expected. Later milestones (cabinet approval, vote, publication)
   usually move prices less than the first credible signal
   ([Schwert 1981](https://www.journals.uchicago.edu/doi/abs/10.1086/466977);
   [Binder 1985](https://www.jstor.org/stable/2555408)).
2. **Exposure drives the direction and spread.** A tax on Spanish banking income hurts a
   bank that earns almost everything in Spain more than one that earns most abroad.
3. **The market as a whole must be removed.** On any day prices move for many reasons;
   the **abnormal return** isolates the company-specific part. The brief defines it as
   the stock’s return minus the IBEX 35’s, over the event day plus the next trading day.

#### 5.3 The Brief’s Example, Reproduced

The brief’s numbers for 12 July 2022, when Spain announced temporary levies on banks and
energy firms, were reproduced exactly from yfinance
([c01_check.py](reversa-2026-10/evidence/c01_check.py)):

| Company | Brief | Measured day-0 return | Abnormal return, day 0 + day 1 |
| --- | --- | --- | --- |
| CaixaBank | −8.6% | −8.63% | −6.94% |
| Sabadell | −7.4% | −7.44% | −5.91% |
| Bankinter | −5.0% | −5.08% | −3.62% |
| BBVA | −3.7% | −3.77% | −2.16% |
| Santander | −3.7% | −3.65% | −2.97% |
| Naturgy | −0.7% | −0.74% | +1.15% |
| Endesa | −0.6% | −0.63% | −0.21% |
| Iberdrola | −0.2% | −0.25% | −1.07% |
| Repsol | not shown | −5.73% | −4.32% |

Two findings follow. First, the brief’s figures are raw close-to-close returns from the
same source the scorers almost certainly use, while scoring uses abnormal returns over
two days; the two differ by several points. Second, the bank ordering matches exposure:
the most domestic lenders (CaixaBank, Sabadell) fell most; Santander and BBVA, which earn
most of their income abroad, fell least. That fits the published event study on this
announcement, where high-tax, smaller, profitable banks fell more
([Martins 2025](https://link.springer.com/article/10.1057/s41261-024-00246-x)).

Why utilities barely moved is less certain. Plausible explanations, untested here: the
energy levy was anticipated (the EU recommended windfall taxes in March 2022 and Spain
had already clawed back utility profits in September 2021), and it was small relative
to their value. Repsol, the oil company, did fall sharply.

The episode also shows why stage matters. The levy became law through **group bill
122/000247**, filed by PSOE and Unidas Podemos on 28 July 2022, published as
**Ley 38/2022** on 28 December 2022. **Ley 7/2024** (21 December 2024) then replaced it
with a permanent tax on interest margins and commissions. Each of these dates is a
candidate event, and they come from the same Congress and BOE data used in Challenge 02.

#### 5.4 What You Build and How It Is Scored

| Layer | Task |
| --- | --- |
| 1. Signal | At least 30 regulatory milestones hitting listed Spanish companies (announcement, cabinet approval, vote, publication), with news volume and tone around each |
| 2. Explain | Model the abnormal return; rank variables such as stage, surprise, media noise, vote margin and company exposure |
| 3. Simulate | For one pending rule and one company, 10,000 Monte Carlo scenarios; impact in € as P10/P50/P90 |

Submission: `event_id, ticker, direction (+1/−1), abnormal_return_pct, p10, p90`.

| Metric (10 hidden past events) | Bad | Good | Excellent |
| --- | --- | --- | --- |
| Direction hit rate | under 55% | 65%+ | 75%+ |
| 80% interval contains the real move | under 50% or absurdly wide | 70–90% | 75–85% and narrow |
| Variable ranking | changes when one event is dropped | stable on hidden events | stable and explains 2022 |

Disqualified for looking up the real prices of test events, using raw returns, or
hand-picking events.

#### 5.5 Data

All checked on 2 October unless marked reported (details in
[data-sources.yaml](reversa-2026-10/data-sources.yaml)):

- **Prices:** yfinance, `^IBEX` and `.MC` tickers (verified).
- **Milestones:** Congress initiative stages (verified), BOE API with publication dates
  (verified), La Moncloa Council of Ministers references (verified; URLs are irregular, so
  crawl the index).
- **News:** the GDELT DOC API covers only the last 3–12 months and rate-limits to one
  request every five seconds; history back to 2015 needs GDELT’s raw GKG files or
  Google BigQuery (reported).
- **Exposure:** company disclosures to the CNMV, the securities regulator, and annual
  reports (reported).

#### 5.6 Traps

- **Ten events is a tiny test.** Each event is 10 points of hit rate; luck dominates.
  Several tickers per event help only partly because they are correlated.
- **Same-date firms are not independent.** When five banks react to one announcement,
  that is closer to one observation than five; standard tests over-reject
  ([Kolari and Pynnönen 2010](https://ideas.repec.org/a/oup/rfinst/v23y2010i11p3996-4025.html)).
  Variable rankings built on such data look more stable than they are.
- **Leaks and timing.** News can leak before an announcement, and announcements after
  the close move the next day (hence the two-day window).
- **Systematic event selection.** To avoid the hand-picking disqualification, define the
  event list by a rule (for example, every decree-law or law in sectors with listed
  companies over a period) before looking at returns.

#### 5.7 Approach

Use market-adjusted returns exactly as defined. Predict direction from the event’s
content (a tax or cap is almost always negative for the targeted sector). Predict size
from exposure (share of income in Spain, tax base relative to market value), stage and
surprise. Calibrate the 80% interval on held-out events with conformal prediction. Build
the Monte Carlo layer on an expected-value model: probability of passage (from
Challenge 02’s ideas) × timing × cost ÷ market value.

### 6. Challenge 02: Bill-to-Law Predictor

#### 6.1 The Problem in Plain Words

For a bill, using only what was known on the day it was filed, predict: (1) the
probability it is published in the BOE as law, (2) the days from filing to publication,
and (3, bonus) which articles survive, change or disappear. Companies and public affairs
teams want to know whether there is still time to shape a bill.

Submission: `initiative_id, p_law, days_to_boe`; bonus `initiative_id, article,
survives / changed / removed`.

| Metric (40 hidden bills) | Bad | Good | Excellent |
| --- | --- | --- | --- |
| Pass or fail (Brier, AUC) | does not beat the baseline | beats it clearly | AUC above 0.85 |
| Timing (mean error in days) | over 120 | under 90 | under 45 |
| Final form, bonus (F1 on articles) | under 0.3 | 0.5 | 0.7+ |

The baseline is “government bill passes, group bill fails”. Disqualified for using
anything after the filing date.

#### 6.2 What Decides Whether a Bill Passes: First Principles

A bill becomes law if, before parliament dissolves, enough deputies vote for it and the
people who control the agenda let it reach the vote. So the drivers are:

1. **Who proposed it.** The government has a majority behind it by definition (it
   survived an investiture vote) and controls much of the agenda. Groups outside
   government usually do not.
2. **How much support it starts with.** A bill signed by several groups, or by the
   governing party’s group, starts closer to a majority.
3. **Who controls the agenda.** The Mesa decides deadlines; a majority on the Mesa can
   freeze opposition bills indefinitely.
4. **Time left.** A bill filed late in a legislature may be caught by dissolution.
5. **How strong the government is.** A majority government passes nearly everything; a
   fragile minority loses bills to rejection, freezing and early elections.
6. **Special procedures.** Budgets have fixed calendars; decree-law conversions often
   lapse; organic laws need 176.

#### 6.3 Measured: How Good Is the Baseline?

This research downloaded every government bill (121) and group bill (122) for
legislatures V–XV, plus Senate, regional and popular-initiative bills for legislatures X,
XII, XIV and XV (4,148 initiatives in all), from the Congress search endpoint
([scan.py](reversa-2026-10/evidence/scan.py), [base-rates.txt](reversa-2026-10/evidence/base-rates.txt)).
For bills with a final outcome:

| Legislature | Years | Govt bills passed | Group bills passed | Baseline accuracy |
| --- | --- | --- | --- | --- |
| V | 1993–96 | 112 of 130 (86%) | 17 of 140 (12%) | 87% |
| VI | 1996–2000 | 172 of 192 (90%) | 28 of 300 (9%) | 90% |
| VII | 2000–04 | 173 of 175 (99%) | 16 of 322 (5%) | 96% |
| VIII | 2004–08 | 140 of 152 (92%) | 18 of 235 (8%) | 92% |
| IX | 2008–11 | 120 of 147 (82%) | 17 of 292 (6%) | 90% |
| X | 2011–15 | 160 of 163 (98%) | 6 of 216 (3%) | 98% |
| XII | 2016–19 | 18 of 49 (37%) | 15 of 333 (5%) | 88% |
| XIV | 2019–23 | 89 of 155 (57%) | 20 of 334 (6%) | 82% |
| XV (closed only) | 2023– | 21 of 25 (84%) | 10 of 143 (7%) | 92% |

Overall the baseline is right on **90.8%** of 3,594 closed bills, which is why the brief
says it is “right more often than you would think”. The XIV figure of 89 of 155 matches
[Newtral’s](https://www.newtral.es/leyes-legislaturas-congreso/20230606/) independent
count.

It fails in two places:

- **Government bills that fail:** 184 in total, of which 158 lapsed at dissolution
  (“caducado”). Only 8 were rejected outright. Failures concentrate in short,
  fragmented legislatures (XII: 31 of 49; XIV: 66 of 155).
- **Group bills that pass:** concentrated in a few kinds
  ([explain.py](reversa-2026-10/evidence/explain.py)):

| Kind of bill | Pass rate | Bills |
| --- | --- | --- |
| Group bill signed by the governing party’s group | 45.8% | 153 |
| Group bill not signed by it (excluding committees) | 2.6% | 2,228 |
| Group bill signed by two or more groups | 47.8% | 69 |
| Group bill from a single group | 4.1% | 2,312 |
| Committee-authored bill | 83.3% | 24 |
| Government bill, majority government | 98.5% | 338 |
| Government bill, minority government | 79.0% | 851 |
| Government bill filed after the third year | 70.0% | 170 |
| Government bill from a decree-law, XII and XIV | 19 of 80 (24%) | 80 |

Other bill types rarely pass (closed bills in legislatures X, XII, XIV and XV): Senate
bills 4 of 30, regional-parliament bills 5 of 76, popular initiatives 2 of 129.

Note that in legislature XV, 90 of 115 government bills were still pending on
1 October 2026, so “government bill passes” is far from safe for current bills.

#### 6.4 Measured: A Simple Model Beats the Baseline

A logistic regression with 11 features, all known on the filing date, was tested by
leaving each legislature out in turn ([experiment.py](reversa-2026-10/evidence/experiment.py)).
Features: government bill; signed by the governing party’s group; number of signing
groups; committee-authored; years since the legislature began; years beyond the third;
organic law; majority government; and three interactions.

| Held-out legislature | Bills | Baseline AUC | Baseline Brier | Model AUC | Model Brier |
| --- | --- | --- | --- | --- | --- |
| V | 270 | 0.870 | 0.130 | **0.941** | **0.102** |
| VI | 492 | 0.896 | 0.098 | **0.956** | **0.082** |
| VII | 497 | 0.954 | 0.036 | **0.986** | **0.019** |
| VIII | 387 | 0.917 | 0.078 | **0.954** | 0.079 |
| IX | 439 | 0.893 | 0.100 | **0.951** | **0.065** |
| X | 379 | 0.975 | 0.024 | **0.993** | **0.017** |
| XII | 382 | 0.728 | 0.120 | **0.909** | **0.086** |
| XIV | 489 | 0.821 | 0.176 | **0.908** | **0.117** |
| XV (closed) | 167 | 0.824 | 0.084 | **0.968** | **0.057** |

The model beats the baseline’s AUC in every legislature and clears the brief’s
“excellent” bar (0.85) in all of them. The largest feature weights are “government
bill” (+2.58, standardized), its interaction with majority government (+1.12), the
governing party’s signature (+0.65), and time elapsed in the legislature (−0.52). Gradient
boosting did not beat logistic regression here.

Caveats, stated plainly. The governing-party mapping per legislature was coded by hand
(including the June 2018 change of government); closed XV bills skew towards quick
outcomes such as rejected consideration votes; and the 40 hidden bills may be chosen to
be harder than a random sample. Expect lower real scores, still with a clear margin.

#### 6.5 Measured: Timing

Matching approved bills from legislatures XII, XIV and XV to their BOE laws by title
(144 of 177 matched; [timing.py](reversa-2026-10/evidence/timing.py)):

| Group | Bills | Median days filing → BOE | 10th–90th percentile | MAE of always guessing the median |
| --- | --- | --- | --- | --- |
| All | 144 | 244 | 64–437 | 110 |
| Government bills | 114 | 240 | 65–422 | 103 |
| Group bills | 27 | 254 | 42–538 | 134 |
| From decree-law | 17 | 278 | 113–510 | 103 |
| Budget bills | 5 | 79 | 64–92 | 7 |

A constant guess misses by about 110 days, between “bad” (over 120) and “good” (under
90). Getting under 90 needs features: budget calendar, urgency, decree-law origin,
legislature fragmentation, time remaining before the four-year limit, and EU
transposition deadlines (bill titles often name the directive). The levy bill above took
153 days.

#### 6.6 Features That Are Legal on the Filing Date

| Feature | Source | Status |
| --- | --- | --- |
| Type (121/122/124/125/120) | Initiative ID | Legal |
| Author(s); count of signing groups; governing party among them | Listing `autor` | Legal |
| Committee authorship | Listing `autor` | Legal |
| Filing date; days since legislature start; days to the four-year limit | Listing `fecha_presentado` | Legal |
| Organic, budget, decree-law origin, directive transposition | Title words | Legal |
| Government seat share; majority or minority; coalition partners | Election results and investiture records | Legal |
| Signers’ combined seats; agreement of signers with the governing bloc in votes before filing | Roll-call votes before filing | Legal (votes from December 2011) |
| Government consent needed (budgetary effect, Article 134.6) | Title words such as tax cuts | Legal, approximate |
| Urgent procedure | Decided at qualification, after filing | ⚠️ Ask the organizers |
| Qualification date | After filing | ⚠️ Ask the organizers |
| Consideration vote, amendment counts, deadline extensions, committee | After filing | ❌ Leakage |
| Actual dissolution date of the legislature | After filing | ❌ Leakage |

#### 6.7 The Bonus: Which Articles Survive

Compare the filed text (BOCG series A for government bills, series B for group bills)
with the BOE text, which the BOE API serves split into blocks and articles.
[ParlLawSpeech](https://parllawspeech.org/data) already links 4,188 Spanish bills
(1996–2023) to 1,563 laws with full texts for both, which gives ready-made training pairs
(GESIS download, probably needing a free account; confirm that `bill_text` is the filed
version). Align
articles by number and wording, then label each as survives (near-identical), changed or
removed. Text reuse between drafts and final laws is an established method
([Gava and co-authors 2021](https://onlinelibrary.wiley.com/doi/abs/10.1111/1475-6765.12395)).
Spain records no amendment outcomes, so labels must be computed
([Palau and co-authors 2026](https://pmc.ncbi.nlm.nih.gov/articles/PMC13080642/)). This is
the same alignment skill as Challenge 03, and it adds difficulty credit.

#### 6.8 Prior Work

US research reaches AUC 0.96 by combining context with bill text and testing on later
Congresses ([Nay 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5425031/)); text and
context are complementary across state legislatures
([Eidelman and co-authors 2018](https://arxiv.org/abs/1806.05284)); GovTrack published
commercial enactment probabilities from 2016 to 2023. For Spain, minority governments
historically passed 88% of their bills, about as many as majority ones, until
fragmentation after 2015
([Field, LSE EUROPP 2019](https://blogs.lse.ac.uk/europpblog/2019/04/25/do-spains-minority-governments-work/)).
No public Spanish bill-passage predictor was found.

### 7. Challenge 03: Influence Graph

#### 7.1 The Problem in Plain Words

An **amendment** is a proposed edit to a draft law: numbered, with the original sentence
and the changed sentence side by side (see [section 2.2](#22-the-european-union) for who
tables them). The challenge asks: when an MEP tables an amendment, did a lobby
submission write it? Prove it even when the words were changed. Then turn those links
into a map of who wins, and predict which consultation suggestions end up in the final
law.

| Step | Task | Submission |
| --- | --- | --- |
| 1. Match | Score each amendment–submission link, paraphrases included | `pair_id, influence_score (0–1)` |
| 2. Weigh | Graph of organizations, MEPs and amendments; who wins most | Demo |
| 3. Predict | Probability each consultation proposal ends up in the final law | `proposal_id, p_adopted (0–1)` |

| Metric | Bad | Good | Excellent |
| --- | --- | --- | --- |
| Precision in your top 20 of 60 hidden pairs | matches boilerplate | 70%+ | 90%+, paraphrases included |
| Recall on the 30 real pairs | under 40% | 60%+ | 80%+ |
| Adoption prediction (AUC) on 20 proposals | about 0.5 | 0.65+ | 0.75+ |

At 19:00 Reversa publishes 60 pairs (30 real influence, 30 lookalike decoys) and 20
proposals. Disqualified if pairs are labelled by hand rather than by the system.

What each step means:

- **Step 1, match (most of the score).** Each of the 60 pairs is one amendment plus one
  lobby submission. Your system gives each pair a score from 0 to 1 for how likely the
  amendment came from that submission. **Precision** asks: of your 20 highest-scored
  pairs, how many are real? **Recall** asks: of the 30 real pairs, how many did you flag
  as real?
- **Step 2, weigh (demo only).** Draw the matches as a network: organizations, MEPs and
  amendments as dots, “copied from” as lines. Then answer who wins most often.
- **Step 3, predict.** For 20 suggestions made in a consultation, give the probability
  each ended up in the final law. AUC checks whether you rank the ones that made it above
  the ones that did not (0.5 is coin-flip guessing).

#### 7.2 A Real Case: Amazon and the GDPR

The Commission’s 2012 GDPR draft said in Article 26, paragraph 1:

> Where a processing operation is to be carried out on behalf of a controller, the
> controller shall choose a processor providing sufficient guarantees …

In plain words: if a company hires another company to handle people’s personal data (for
example a cloud host storing its files), it must pick one that protects that data
properly.

Amazon’s lobby paper proposed inserting, after “on behalf of a controller”:

> … **and which involves the processing of data that would permit the processor to
> reasonably identify the data subject** …

That narrows the rule: the obligations would apply only when the hired company could
actually tell who the person is, which suits a cloud provider storing data it cannot
read. Four separate amendments, tabled by different MEPs in three committees, contained
that phrase and were verified by LobbyPlag’s volunteers as copied from Amazon’s paper:
IMCO 333 (Malcolm Harbour), ITRE 614 (Giles Chichester), JURI 259 (Sajjad Karim) and
ITRE 616 (Seán Kelly, Adina-Ioana Vălean and Angelika Niebler)
([lobbyplag-example.txt](reversa-2026-10/evidence/lobbyplag-example.txt)).

The hidden test pairs amendments with consultation submissions rather than papers sent
directly to MEPs, but the matching problem is the same.

#### 7.3 Why Matching Is Hard, Measured on the Amazon Case

The table compares Amazon’s paper with five amendments to the same paragraph, using
Python’s character-similarity ratio (0 means nothing in common, 1 means identical)
([lobbyplag_example.py](reversa-2026-10/evidence/lobbyplag_example.py)):

| Amendment to Article 26(1) | LobbyPlag status | Whole text | Only the changed words |
| --- | --- | --- | --- |
| ITRE 616 (Kelly, Vălean, Niebler) | Verified copy | 0.96 | 0.67 |
| ITRE 615 (Rohde, Vălean) | Never checked | 1.00 | 0.98 |
| LIBE 1774 (Vălean, Rohde) | Never checked | 0.95 | 0.65 |
| LIBE 1773 (Alvaro: “a processing operation” becomes “processing”) | Never checked | 0.63 | 0.12 |
| LIBE 1775 (Stadler: a different rewording) | Never checked | 0.60 | 0.06 |

The traps it shows, plus three more:

1. **Everyone quotes the same original sentence.** Lobby papers and amendments both
   repeat the Commission’s text, so even unrelated amendments score about 0.6 on the
   whole text. Compared on only the changed words, the unrelated ones fall to 0.06–0.12.
   Lesson: **compare what each one changes, not the whole text.**
2. **“Not checked” does not mean “not copied”.** ITRE 615 and LIBE 1774 contain Amazon’s
   phrase almost word for word, yet LobbyPlag never marked them. Unchecked candidates
   cannot be used as negative examples without review.
3. **Rewording.** Copies are not always word for word: words get swapped, sentences
   reordered, or text translated.
4. **Standard legal phrasing.** Phrases such as “Member States shall ensure that …”
   appear in thousands of documents, so sharing them proves nothing (the brief’s “trap”).
5. **Same topic, opposite request.** A consumer group and Amazon can both target
   Article 26 yet ask for opposite changes.
6. **Tiny words carry meaning.** “Shall” (must) becoming “may” (allowed to) is a one-word
   edit that reverses the obligation.

#### 7.4 How Influence Is Detected: First Principles

Copying leaves traces. Verbatim copying shares long, rare word sequences; paraphrasing
keeps the structure and meaning but swaps words. The first step is to **extract the
change** on each side (the inserted and deleted words), because the shared original text
inflates any whole-text comparison. A strong detector then compares the changes with
three signals:

1. **Rare shared phrases.** Shared n-grams weighted by how rare they are across a large
   corpus of EU legal text. Boilerplate scores near zero.
2. **Alignment.** Smith-Waterman local alignment finds the best-matching stretch even with
   insertions. A “semantic” variant scores substituted words by embedding similarity, so
   synonyms still align ([Furnas](https://static1.squarespace.com/static/59e25521b7411c07ef1410fa/t/5d499af08dc10f0001ab7e1d/1565104881203/Furnas_SemanticSmithWaterman.pdf)).
   The same paper warns that “shall” to “may” looks tiny to embeddings but reverses legal
   meaning; legal modal verbs need their own handling.
3. **Meaning and direction.** Sentence embeddings or a language model judge whether the
   amendment makes the same *change* the submission asked for (adding an exemption,
   deleting an obligation), not merely discusses the same article.

Decoys are probably pairs that share topic and boilerplate but not the specific change,
so signal 3 is likely what separates good from excellent.

#### 7.5 Data

All verified on 2 October except where noted:

- **Submissions:** the Have Your Say API returns every initiative, its consultation
  stages and every feedback item with organization, type, country and attachments. For
  the AI White Paper (initiative 12270), publication 12902 had 1,216 responses. The
  substance is often in PDF attachments, in many languages.
- **Amendments:** Parltrack dumps (ODbL licence). Plenary amendments: 49,201 records with
  old text, new text, the article targeted, procedure reference and committee; authors
  on about 28%. The committee-amendment dump is larger (about 120 MB compressed).
- **Votes and adoption in plenary:** HowTheyVote.eu weekly CSV releases, including
  amendment authors.
- **Final law:** EUR-Lex through the CELLAR SPARQL endpoint (responds).
- **Organizations:** Transparency Register (reported) and LobbyFacts (site up).
- **A labelled practice set:** the [LobbyPlag data repository](https://github.com/lobbyplag/lobbyplag-data)
  holds the GDPR amendments, 1,159 lobby proposals from 76 documents by 44 lobbyists, and
  1,976 candidate proposal–amendment matches. 175 are human-checked and verified real
  matches; the other 1,801 were never checked, so they are not confirmed negatives.
  Decoys can be built by pairing amendments with proposals on the same article that were
  not matched, after review, because some unchecked amendments are copies
  ([section 7.3](#73-why-matching-is-hard-measured-on-the-amazon-case)). This is the
  closest public analogue to the hidden test.
- **Final EU texts linked to bills:** ParlLawSpeech’s European Parliament component
  (14,105 bills, 10,554 laws, 1999–2024; reported).

#### 7.6 Prior Work

- **LobbyPlag (2013)** found GDPR amendments copied from lobby papers; some MEPs had
  22–25% of their amendments containing lobby text
  ([Open Knowledge](https://blog.okfn.org/2013/03/22/lobbyplag-who-is-really-writing-the-law/)).
- **The Legislative Influence Detector** used Elasticsearch to find candidates, then
  Smith-Waterman to confirm; it found 14,137 model-bill-to-bill reuse instances in US
  states ([Burgess and co-authors, KDD 2016](https://dl.acm.org/doi/abs/10.1145/2939672.2939697)).
- **Text as Policy** validated alignment scores against ideology and policy categories on
  500,000 bills; code is public
  ([Linder and co-authors 2020](https://onlinelibrary.wiley.com/doi/abs/10.1111/psj.12257)).
- **Klüver** measured EU lobbying success by comparing consultation positions with final
  policy across 56 issues and 2,696 groups
  ([2009](https://journals.sagepub.com/doi/10.1177/1465116509346782)), the precedent for
  the adoption step.

No public study tracing AI Act amendments to lobby submissions with text methods was
found.

#### 7.7 Operational Traps

- **The input format is unknown.** If pairs arrive as IDs, the system must fetch amendment
  and submission text, including PDF extraction, within the hour.
- **Multilingual submissions.** Translate or use multilingual embeddings.
- **Twenty proposals is a tiny test** for adoption AUC.
- **Unclear rule on the final text.** For past laws the final text exists. Comparing a
  proposal with it is measurement, not forecasting. The brief does not forbid it, but
  ask before relying on it.

### 8. The Sponsor: What Reversa Wants

Reversa, founded in 2025 in Madrid, sells an “operating system for regulation”:
monitoring of 500+ official sources, sector-specialized AI agents, and Legislative Twins
that follow EU procedures from proposal to enforcement
([Built in Europe profile](https://builtineurope.substack.com/p/turning-regulatory-chaos-into-structured-intelligence-reversa)).
Its customers are multinationals, public affairs consultancies, Big Four firms and law
firms. A credible bill-passage probability or influence map is a feature they could
sell; a clear demo that a lawyer can follow is what the founders will judge.

### 9. What Already Exists: Reversa’s Public Work and Other Teams

Checked on 2 October 2026 across GitHub, Hugging Face, Kaggle and Reversa’s site:

- **Reversa publishes no code or data.** Its probable GitHub organization
  [`reversa-ai`](https://github.com/reversa-ai) (created 8 April 2026) has no public
  repositories or members; its profile changed on 18 September, so it is in use
  privately. No Hugging Face presence. A September research note found the same
  ([jlevy/thinking](https://github.com/jlevy/thinking/blob/main/docs/project/research/research-2026-09-02-madrid-open-reversa-challenge.md)).
- **Reversa’s product does not yet claim any of the three capabilities.** Its site lists
  Regulatory Map, Agentic Radar, Legislative Twins, obligation tracking and impact
  analysis, but nothing on bill-passage prediction, market impact or lobby tracing. Its
  founding-engineer posting describes “a knowledge graph infrastructure of global
  regulation” navigated by agents that “predict what is coming”, built because “none of
  it exists off the shelf”. This matches the brief: these are problems Reversa is working
  on, not solved ones.
- **No other team’s work on these challenges is public.** Repository searches for the
  event and for each challenge returned nothing. Code mentioning `reversa.ai` belongs to a
  job applicant’s EU-compliance RAG prototype (`RodrigoCovas/regula`) and an unrelated
  payments project. Two Spanish Congress speech datasets on Hugging Face updated in late
  September (`Tridente-ETSISI/discursos-congreso-es`, `Cinkui/discursos-congreso-es`)
  are 1,088-speech samples for a university data-mining course.
- **Two useful public datasets surfaced from this search:** the LobbyPlag data
  repository (Challenge 03 practice set, section 7.5) and ParlLawSpeech (bill and law
  texts for Spain and the EU, sections 6.7 and 7.5).

## Key Insights

- **The baseline is strong because Spanish politics is structured, and it fails for
  structural reasons too.** Nearly all its errors are government bills killed by
  dissolution and group bills carried by the governing party or by several groups. Each
  of those is visible on the filing date.
- **The decisive mechanism in today’s Congress is agenda control, not votes.** Group bills
  are frozen at the amendment stage unless the governing party signs them. A model that
  encodes “who controls the Mesa” captures what a vote-counting model misses.
- **The organizers used yfinance raw close-to-close returns in their example.**
  Reproducing their exact numbers removes one source of scoring mismatch for Challenge 01.
- **Challenges 01 and 02 share their data spine.** Congress stages and BOE dates provide
  both the bill outcomes and the market event dates; the bank levy is one example running
  through both.
- **Challenge 02’s bonus and Challenge 03 are the same skill:** aligning two versions of
  legal text and telling a real change from boilerplate.
- **Small hidden tests (10 events, 20 proposals) reward calibration and robustness over
  cleverness.** Luck dominates there; the 40-bill and 60-pair tests are less noisy.

## Comparison Matrix

| Criterion | Open track | 01 Law × Markets | 02 Bill-to-Law | 03 Influence Graph |
| --- | --- | --- | --- | --- |
| Scored by | Jury only | 10 hidden events | 40 hidden bills | 60 pairs plus 20 proposals |
| Reversa difficulty | — | 4/5 | 4/5 | 5/5 |
| Data path verified | ✅ | ✅ prices; ⚠️ news history | ✅ complete | ✅ mostly; ⚠️ PDF text |
| Evidence we can win the metric | — | Reproduced the example | **Measured AUC 0.91–0.99 on held-out legislatures** | Practice set found (175 verified GDPR pairs); not yet tested |
| Luck in the hidden test | — | High | Moderate | Moderate (pairs), high (adoption) |
| Risk in the 19:00–20:00 hour | Low | Medium (event to ticker mapping) | Low (IDs to features is mechanical) | High (unknown input format) |
| Likely competition | Low | Medium | High (most “standard ML”) | Low |
| Fit with this repository | High (Congress data, review UI) | Low | Medium (data and evaluation habits) | Medium (transcript-to-record text alignment) |

## Options Considered

### Option A: Challenge 02, Bill-to-Law (Recommended)

**Description:** Filing-date model for passage plus timing model, bonus article layer if
time allows.

**Pros:**
- The only option with measured evidence of “excellent” performance on held-out data
- Every data source is verified, including historical labels for 30 years
- The 19:00 hour is mechanical: bill IDs to listing data to features to CSV
- Directly useful to Reversa’s customers; easy to explain to a lawyer
- The bonus layer adds difficulty credit and reuses alignment skills

**Cons:**
- Probably the most popular choice; competent teams will also beat the baseline
- Timing below 90 days MAE is not yet demonstrated
- The hidden 40 may be harder than average

### Option B: Challenge 03, Influence Graph

**Description:** Rare-phrase, alignment and meaning signals to rank 60 pairs; adoption
model for 20 proposals.

**Pros:**
- Highest difficulty credit (5/5); likely fewer competitors
- Pair ranking suits modern language models well
- Closest to Reversa’s Legislative Twins product

**Cons:**
- Only one labelled practice set (GDPR, 2013), with verified positives but no confirmed
  negatives
- Unknown pair format; PDF and multilingual extraction under time pressure
- Adoption AUC on 20 items is mostly luck

### Option C: Challenge 01, Law × Markets

**Description:** Event dataset, abnormal-return model, Monte Carlo layer.

**Pros:**
- The scoring formula is exactly reproducible
- Strong demo (euros at stake, P10/P50/P90)

**Cons:**
- Ten test events: each is 10% of the hit rate
- Building 30+ systematic events is manual work in a one-hour data window
- Historical news tone needs BigQuery or bulk files

### Eliminated Options

- **Open track:** Eliminated as a first choice because it has no hidden test and Reversa
  says much of it is already solved. Keep the Junts early-warning finding as a demo
  flourish or a feature for Challenge 02.
- **A new idea of our own:** Allowed by the second email, but scoring “against actual
  outcomes and other teams” favours a defined challenge.

## Recommendations

Pick **Challenge 02**, aim for the bonus layer, and use one Challenge 01 or open-track
insight in the demo story. The reasoning is simple: 60% of the score is the hidden test,
and Challenge 02 is the only option where this research has already shown, on real
held-out data, a model clearing the top tier.

If the team prefers a higher-variance bet with more difficulty credit, Challenge 03 is the
alternative; decide that only if someone on the team is confident with PDF extraction and
EU document plumbing.

## Next Steps

- [ ] Reply to Tomás today with the team and the pick, plus the organizer questions below
- [ ] Confirm whether code and data may be prepared before Saturday
- [ ] If allowed: script “bill ID → listing record → features → CSV” for all
      legislatures, and rehearse it on held-out bills with a one-hour timer
- [ ] Add timing features and check MAE against the 90-day bar
- [ ] Build the bonus article alignment (BOCG text vs BOE blocks)
- [ ] Draft the five-minute demo: one bill, its probability, the reasons, and the timing
- [ ] Write the team brief for the chosen challenge in this repository

### Questions for the Organizers

1. May we prepare code and download public data before Saturday?
2. Challenge 02: Are the 40 bills closed (final outcome known)? Which types and
   legislatures? Is the qualification date or the urgent-procedure flag allowed? How is
   `days_to_boe` scored for bills that did not pass?
3. Challenge 03: Do pairs arrive as text or as IDs? May the adoption step compare proposals
   with the final adopted text?
4. Challenge 01: Is the event day’s return close-to-close against `^IBEX`?
5. Open track: Does it compete for the same prize?

## Methodology

Sources were searched on the web and, where possible, fetched directly: Congress open data
files and its internal search endpoint, the BOE API, Have Your Say API, Parltrack dumps,
HowTheyVote releases, EUR-Lex SPARQL, GDELT and yfinance. Each source in the catalog says
whether it was verified live. Measurements were computed with the scripts in
[evidence/](reversa-2026-10/evidence/README.md); figures reported by others are cited.
Papers marked `cited` in the catalog were not read in full.

Existing work was searched on GitHub (organization, repository and code search), Hugging
Face (datasets, models, organization) and Kaggle, and on Reversa’s own site, news and
careers pages.

Known gaps: GDELT history was not tested because of rate limiting; the ParlLawSpeech
download was not tested (GESIS refused an anonymous request); the Transparency
Register export and CNMV disclosures were not fetched; the Martins (2025) and Italian
(2023) event studies were read only through abstracts; the coalition-agreement series uses
142 of roughly 200 legislature-XV sessions; bill–law timing matches cover 144 of 177
approved bills.

## References

- Full source list with access details: [data-sources.yaml](reversa-2026-10/data-sources.yaml)
- Full prior-work list with findings: [prior-work.yaml](reversa-2026-10/prior-work.yaml)
- Measurement scripts and outputs: [evidence/](reversa-2026-10/evidence/README.md)
- Organizer brief: [madrid-open-reversa-challenges.pdf](../brief/madrid-open-reversa-challenges.pdf) (shared by email)
- [Congreso open data](https://www.congreso.es/es/datos-abiertos) (official)
- [BOE consolidated legislation API](https://www.boe.es/datosabiertos/api/legislacion-consolidada) (official)
- [Have Your Say portal](https://have-your-say.ec.europa.eu/index_en) (official)
- [Parltrack dumps](https://parltrack.org/dumps/) (community, ODbL)
- [Nay 2017, PLOS ONE](https://pmc.ncbi.nlm.nih.gov/articles/PMC5425031/) (peer-reviewed)
- [Burgess and co-authors 2016, KDD](https://dl.acm.org/doi/abs/10.1145/2939672.2939697) (peer-reviewed)
- [Martins 2025, Journal of Banking Regulation](https://link.springer.com/article/10.1057/s41261-024-00246-x) (peer-reviewed; abstract only)
- [Demócrata, 17 January 2025](https://www.democrata.es/demodata/no-psoe-no-boe-la-mesa-del-congreso-bloquea-en-fase-de-enmiendas-todas-las-proposiciones-de-ley-sin-firma-socialista/) (data journalism)

<!-- This document follows common-doc-guidelines.md.
See github.com/jlevy/practical-prose and review guidelines before editing.
-->
