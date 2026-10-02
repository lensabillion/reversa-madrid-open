---
name: influence-architecture
description: >-
  Fit a feature into the agreed seven-part Influence Graph architecture before building
  it: load, extract the change, signals, combine into pairs.csv, graph, adoption into
  proposals.csv, demo, and the practice loop. Use it before you plan, design or write
  code for any feature, bead or pull request in this repository (backend, frontend,
  pipeline, scoring, matching, graph, adoption, demo, data loading or evaluation), even
  when the request never mentions the architecture. Use it also whenever code in attic/
  or another earlier prototype looks reusable.
---

# Fit Every Feature Into the Architecture

The design is decided: seven parts plus a practice loop, described in
[explainer §11](../../../docs/explainer/influence-graph-primer.md#11-proposed-architecture).
Every feature belongs to one of those parts.
Run this check before building, so that what you build is the part we agreed to build.

Why it matters: on 2 October, work that passed every gate still drifted from the design.
Two pull requests of demo screens (#12 and #13, about 2,500 added lines) came before the
command that writes the scored CSVs, and the graph was built from LobbyPlag's 2013
volunteer labels instead of from our own scores.
Linters, types and tests check how code is written.
Only this check asks whether it is the right code in the right place.

## The Architecture on One Screen

| Part | Its job | What it hands on |
| --- | --- | --- |
| 1 · Load | Fetch inputs by ID, turn PDFs into text, detect the language, translate if needed | Clean text with its source |
| 2 · Extract the change | Diff the amendment against the original law; find the matching passage in a long paper | The edits, and the passages to compare |
| 3 · Signals | Rare shared phrases, alignment, character similarity, same edit in the same direction, embeddings of the changes, a legal-word check (shall, may); optionally a language-model or Jev judge | One number per signal per pair |
| 4 · Combine | A small trained model gives a calibrated score from 0 to 1 | `pairs.csv` |
| 5 · Graph | Organizations, MEPs and amendments; win rates | The influence graph |
| 6 · Adoption model | Predicts which consultation proposals reach the final law | `proposals.csv` |
| 7 · Demo app | Tracer, map, scoreboard | What the jury sees |
| Practice loop | LobbyPlag's labelled pairs, simulated tests of 30 real and 30 decoy pairs | Trains and checks part 4 |

The arrows: the 19:00 inputs go through parts 1, 2, 3 and 4 in that order.
The practice loop feeds part 4. Part 4 feeds the graph (5).
The graph and the inputs feed adoption (6). The graph feeds the demo (7).
Parts 1–4 produce the first CSV and part 6 the second; parts 5 and 7 serve the demo.

Three design rules come with it:

- **Raw model output stays separate from labels.** Every score is saved with the signals
  that produced it, so the demo can explain it and we can check it.
- **An optional part may fail without stopping the run.** If translation or the judge
  fails at 19:30, the score still comes out from the other signals.
  A missing *required* input is different: it stops the run with a clear error
  (`AGENTS.md`, "Errors are explicit").
- **No hand labelling, anywhere.** The pipeline writes the CSVs; people only press run.

## Before You Design or Write Code

1. **Read the state.** `docs/implementation-status.md` says what is built, decided and
   open. Then read the part of §11 your work touches.
2. **Name the part.** Write it in the bead.
   If the feature fits no part, stop and ask the user: it is either out of scope or a
   change to the architecture, and only the project owner changes the architecture.
3. **Extend the part's existing home.** Search the code for what already does this job
   and build on it. Keep one implementation per job: a second matcher, loader or graph
   builder splits the effort and leaves two things half done.
   If the existing one is wrong, fix or replace it in place, with evidence.
4. **Follow the arrows.** A part takes its inputs only from the parts drawn before it.
   - The graph is built from our scored links, never from historical labels such as
     LobbyPlag's verified flags. Labels train and check part 4; the demo may show them
     beside our output as a comparison, marked as such.
   - The demo calls the pipeline's parts; it holds no scoring logic of its own.
   - Every part runs without the web server, because the 19:00 command calls the parts
     directly. FastAPI routes stay thin adapters over the services.
5. **Check that it moves the score.** The hidden test is 60% of the event, and only parts
   1–4 and 6 reach it. Until one command turns the 19:00 inputs into both validated
   CSVs, work on that path comes first (explainer §10: a model that is not finished at
   19:00 is worth nothing). If you are asked for demo work before then, name the
   trade-off to the user before starting.
6. **Leave open decisions open.** The Decisions table in `docs/implementation-status.md`
   lists them. Do not settle one in code: no language-model calls before the judge is
   decided (D1), and no hard-coded input format before the organizers answer (D5).
   Build so the decision can land later, and ask.
7. **Measure scoring changes.** A change to parts 2, 3, 4 or 6 is accepted on
   practice-loop evidence, reported before and after on the same folds and seeds
   (`AGENTS.md`, "Testing and Evaluation").

In the pull request's first paragraph, say which part the change belongs to, what it
takes from the part before and what it hands to the part after.
The reviewer then sees the fit in one line.

## The Earlier Prototype in attic/

`attic/prototype-2026-10-02/` was written before the architecture was decided.
Do not import, copy, port or extend its code, and do not treat its measurements as
describing the code on `main`.
Its useful ideas already appear as parts and signals in §11: build them fresh in their
part, under the gates, and keep them only if the practice loop shows a gain.

Public data under `data/` may be used.
If a file there was made by attic code, such as `data/idf.npz`, rebuild it with code on
`main` before a submitted score depends on it, so a fresh checkout can reproduce the
result.

## When a Request Conflicts With the Architecture

Say which part or arrow it breaks, propose the version that fits, and let the user
choose. Do not quietly build either one.
If the user changes the architecture, record the decision in the Decisions table and
update explainer §11 in the same pull request, so the next agent follows the new
version.
