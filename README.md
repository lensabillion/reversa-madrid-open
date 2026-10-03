# Reversa Challenges, Madrid Open 2026

Our entry for Reversa's track at the Madrid Open (Saturday 3 October 2026, Mad Tech Campus).
We compete in **Challenge 03: The Influence Atlas**: an open, public map of who shapes
EU law since 2019. For any law, it shows which organizations' asks reached amendments and
the final text, with the evidence side by side; it ranks who actually wins, explains how,
and forecasts who will win next.

The organizers replaced the first Challenge 03 brief (Influence Graph: score 60 supplied
pairs into CSVs) at kickoff on 3 October 2026. The
[Atlas brief](docs/brief/influence-atlas-challenge-brief.pdf) is the one that counts; the
[first brief](docs/brief/madrid-open-reversa-challenges.pdf) is kept for the record.

## What is scored

There is no hidden test and no supplied data. The jury scores 100 points live at 19:30:

| Criterion | Points | What the jury does |
| --- | ---: | --- |
| Real links | 25 | Picks 3 links from our graph at random and reads both texts side by side |
| Any law | 20 | Names an EU law on the spot; our system shows who shaped it, with no code changes |
| Insight | 25 | Reads our answers to five questions: who, on what, towards what, how, what next |
| Report | 15 | Reads our public report and opens this repository |
| Ambition | 15 | How much of Europe since 2019 we cover, and our forecast |

We hand in a graph the jury can explore live, a short public report, and this repository,
open source so anyone can rerun it.

## Where to Start

- [AGENTS.md](AGENTS.md): how we work, for humans and AI agents alike: the four project
  rules, the PR format, testing and evaluation, and the commands.
- [SUPPLY-CHAIN-SECURITY.md](SUPPLY-CHAIN-SECURITY.md): rules for adding dependencies.
- [Backend guide](backend/README.md): run the evidence API, obtain the public snapshot,
  understand the layers and scoring limits, and verify the implementation.
- [Frontend guide](frontend/README.md): run the evidence workspace and connect it to the API.
- [The Atlas explainer](docs/explainer/influence-atlas-primer.md): the current challenge,
  what changed, the architecture, the data, the models and the plan to win, from first
  principles.
- [The first explainer](docs/explainer/influence-graph-primer.md): written for the first
  brief. Its background on EU law-making, amendments, lobbying and the boilerplate trap
  still holds.

The repository layout is described in AGENTS.md.
