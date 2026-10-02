# Reversa Challenges, Madrid Open 2026

Our entry for Reversa's track at the Madrid Open (Saturday 3 October 2026, Mad Tech Campus).
We picked **Challenge 03: Influence Graph**: given an EU amendment and a lobby
submission, score how likely the amendment was written from the submission, then map who
wins and predict which consultation proposals reach the final law.

## What is scored

| Output | File | Metric |
| --- | --- | --- |
| `pair_id, influence_score` for 60 pairs (30 real, 30 lookalike decoys) | CSV | Precision in our top 20; recall on the 30 real pairs |
| `proposal_id, p_adopted` for 20 consultation proposals | CSV | AUC |
| Influence graph of organizations, MEPs and amendments | Demo | Jury |

Test inputs are published at 19:00 and the CSVs are due at 20:00, so the pipeline must
turn raw inputs into both CSVs with one command.

## Where to Start

- [AGENTS.md](AGENTS.md): how we work, for humans and AI agents alike: the four project
  rules, the PR format, testing and evaluation, and the commands.
- [SUPPLY-CHAIN-SECURITY.md](SUPPLY-CHAIN-SECURITY.md): rules for adding dependencies.
- [The explainer](https://claude.ai/artifact/HL1KzDHpMWYerESyy3pLje): the challenge explained
  from first principles. The page is private; the owner shares it from its Share menu. Its
  source is [docs/explainer/influence-graph-primer.html](docs/explainer/influence-graph-primer.html);
  GitHub shows HTML files as code, so download that file and open it in a browser to read it.

The repository layout is described in AGENTS.md.
