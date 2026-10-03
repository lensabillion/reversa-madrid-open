---
name: influence-architecture
description: >-
  Fit a feature into the agreed Influence Atlas architecture before building it: collect,
  resolve actors, find candidates, verify links, trace outcomes, the atlas graph, analyse
  (rank, explain, forecast), publish (explorer, any-law command, report), and the practice
  loop. Use it before you plan, design or write code for any feature, bead or pull request
  in this repository (backend, frontend, pipeline, data loading, retrieval, scoring,
  matching, outcomes, graph, rankings, forecast, report, demo or evaluation), even when
  the request never mentions the architecture. Use it also whenever code in attic/ or
  another earlier prototype looks reusable.
---

# Fit Every Feature Into the Architecture

The design is eight parts plus a practice loop, described in
[the Atlas explainer, §6](../../../docs/explainer/influence-atlas-primer.md#6-the-architecture).
Every feature belongs to one of those parts.
Run this check before building, so that what you build is the part we agreed to build.

Why it matters: on 2 October, work that passed every gate still drifted from the design.
Two pull requests of demo screens (#12 and #13, about 2,500 added lines) came before the
command that writes the scored output, and the graph was built from LobbyPlag's 2013
volunteer labels instead of from our own scores.
On 3 October the organizers replaced the brief, and the design changed with it: from
scoring 60 supplied pairs to finding and proving links across all EU law since 2019.
Linters, types and tests check how code is written.
Only this check asks whether it is the right code in the right place.

## The Architecture on One Screen

| Part | Its job | What it hands on |
| --- | --- | --- |
| 1 · Collect | For one procedure number, download and normalize its public record: committee and plenary amendments, consultation feedback and position papers (PDF to text, split into passages), the Commission proposal, Parliament's position, the final act, register entries, meetings, votes. Extract each amendment's change (inserted and deleted words) | Normalized records with their source URL, retrieval date and hash, cached under `data/` |
| 2 · Resolve actors | One identity per organization and per MEP across sources: Transparency Register ID first, then normalized names | Actor table with every alias and its source |
| 3 · Find candidates | A cheap, high-recall search per law: index the amendments' changes and the submissions' passages; shortlist the passages each amendment could come from | Candidate pairs with their retrieval score |
| 4 · Verify links | The careful judge, run only on candidates: compare the change with the passage, compute signals (rare shared phrases, alignment, same edit in the same direction, legal polarity, meaning), combine them; publish a link only above the precision threshold | Links with a score, the signals, the evidence spans, and published or unconfirmed status |
| 5 · Trace outcomes | Did the asked change reach Parliament's position and the final article? Align amendments and asks with the final act | For each ask and amendment: heard, adopted by Parliament, won, with the final article's text |
| 6 · Atlas graph | Actor → ask → amendment → final article, plus MEPs, topics, years, meetings and votes; every edge carries its evidence | The graph store the explorer, rankings and report read |
| 7 · Analyse | Rank (wins by topic and year, compared with lobby spend), Explain (positions, channels, public statements against asks), Forecast (who rises, which open asks land), each tested on held-out laws | Rankings, findings and forecasts, each linked to the edges behind it |
| 8 · Publish | The live explorer, the any-law command, the public report and the open repository | What the jury and the public see |
| Practice loop | LobbyPlag's labelled pairs and blind audits of our own published links measure part 4's precision; laws decided later than the training laws test part 7's forecast | Thresholds and accepted model changes |

The arrows: a procedure number goes through parts 1 to 6 in order; part 3 reads part 1
and part 2's records; part 5 reads part 1's final texts and part 4's links.
Parts 6 and 7 feed part 8. The practice loop feeds parts 4 and 7.
The live "any law" check runs parts 1 to 6 for one procedure number and shows it in part 8.

Design rules that come with it:

- **Every edge carries its evidence.** A link stores the ask's passage, the amendment's
  change and, when it won, the final article, with source URLs and character offsets, so
  the jury can read both texts side by side.
- **Show only what we would defend.** The graph shows published links only: those above
  the threshold the practice loop sets for high precision. Lower candidates are kept as
  unconfirmed, labelled as such, and never mixed into rankings.
- **Any law, no code changes.** Every part takes a procedure number and nothing
  law-specific: no per-law code, configuration or hand-picked documents.
- **Raw model output stays separate from labels.** Every score is saved with the signals
  that produced it. Audit labels and LobbyPlag labels measure; they never become edges.
- **An optional part may fail without stopping the run.** If translation, the language
  model judge or a source is down, the run continues and says what is missing.
  A missing *required* input stops the run with a clear error (`AGENTS.md`, "Errors are
  explicit").
- **Nobody edits links, scores or rankings by hand.** People may audit a random sample to
  measure precision.
- **Anyone can rerun it.** Downloads are scripted, pinned and cached; a fresh checkout
  rebuilds the same results.

## Before You Design or Write Code

1. **Read the state.** `docs/implementation-status.md` says what is built, decided and
   open. Then read the part of the explainer's §6 your work touches.
2. **Name the part.** Write it in the bead.
   If the feature fits no part, stop and ask the user: it is either out of scope or a
   change to the architecture, and only the project owner changes the architecture.
3. **Extend the part's existing home.** Search the code for what already does this job
   and build on it. Keep one implementation per job: a second matcher, loader or graph
   builder splits the effort and leaves two things half done.
   If the existing one is wrong, fix or replace it in place, with evidence.
   Code written for the first brief (the comparison service, PDF extraction, the
   submission command, the practice harness) is the starting point of parts 1, 4 and the
   practice loop.
4. **Follow the arrows.** A part takes its inputs only from the parts drawn before it.
   - The graph is built from our verified links, never from historical labels such as
     LobbyPlag's verified flags. The demo may show those labels beside our output as a
     comparison, marked as such.
   - The explorer and the report call the pipeline's parts; they hold no scoring logic.
   - Every part runs without the web server, because the any-law command and the batch
     over all laws call the parts directly. FastAPI routes stay thin adapters.
5. **Check that it moves the score.** The jury scores five things live (brief p. 9):
   real links 25, any law 20, insight 25, report 15, ambition 15.
   Until one command turns a procedure number into verified links with their evidence,
   work on parts 1 to 6 for one law comes first: it carries real links and any law
   (45 points), and insight, report and ambition are built on top of it.
   If you are asked for other work before then, name the trade-off to the user first.
6. **Leave open decisions open.** The Decisions table in `docs/implementation-status.md`
   lists them. Do not settle one in code: no language-model calls before the judge is
   decided (D1), and no licence or public release before D6.
   Build so the decision can land later, and ask.
7. **Measure scoring changes.** A change to parts 3, 4, 5 or 7 is accepted on
   practice-loop evidence, reported before and after on the same folds, samples and seeds
   (`AGENTS.md`, "Testing and Evaluation").

Fill the pull request template's **Architecture and Agreed Decisions** section: for each
change, its part, what it takes from the part before and hands to the part after, and the
agreed decision or design rule it follows.
Name decisions as the Decisions table names them, and quote §6's rules and arrows.
The reviewer can then check every choice against what was agreed, instead of
reconstructing it.

## The Earlier Prototype in attic/

`attic/prototype-2026-10-02/` was written before the architecture was decided.
Do not import, copy, port or extend its code, and do not treat its measurements as
describing the code on `main`.
Its useful ideas already appear as parts and signals in §6: build them fresh in their
part, under the gates, and keep them only if the practice loop shows a gain.

Public data under `data/` may be used.
If a file there was made by attic code, such as `data/idf.npz`, rebuild it with code on
`main` before a published result depends on it, so a fresh checkout can reproduce it.

## When a Request Conflicts With the Architecture

Say which part or arrow it breaks, propose the version that fits, and let the user
choose. Do not quietly build either one.
If the user changes the architecture, record the decision in the Decisions table and
update the explainer's §6 in the same pull request, so the next agent follows the new
version.
