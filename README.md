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

## Layout

| Path | Contents |
| --- | --- |
| `docs/brief/` | The organizers' brief (PDF) |
| `docs/research/` | Research on all three challenges, data-source and prior-work catalogs, evidence scripts |
| `data/` | Downloaded public data (not committed) |
