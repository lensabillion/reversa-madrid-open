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

## Quickstart

You need Python 3.14 and uv 0.12 or later (the Makefile's `UV_EXCLUDE_NEWER` setting needs
it); the [backend README](backend/README.md) has the details. From the repository root:

```sh
make setup                        # once per machine, needs network: Parltrack dumps, the
                                  # Transparency Register and the Have Your Say index
make atlas LAW='AI Act'           # collect one law, then asks, links, outcomes, graph, counts
make coordinated LAW='AI Act'     # near-identical amendments tabled across political groups
make channels LAW='AI Act'        # how the law was lobbied: consultation, timing, MEPs, coalitions
make directions LAW='AI Act'      # which way each amendment moves the law
```

`LAW` takes a procedure number (`2021/0106(COD)`), a CELEX or COM reference, a common
name (`'AI Act'`, `'DSA'`) or a title. Every output is written under
`data/laws/<procedure>/` (for the AI Act, `data/laws/2021-0106-COD/`): `atlas.json`,
`coordinated.json`, `channels.json` and `directions.json`, beside the collected texts,
amendments, submissions and a run manifest. `data/` is never committed; everything in it
comes from public sources and is rebuilt by these commands. `make check` runs every gate.

## Licence

The licence is pending the project owner's decision (D6 in
[implementation status](docs/implementation-status.md#decisions)). Until it is decided,
the repository has no LICENSE file.

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
