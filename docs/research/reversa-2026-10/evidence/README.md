# Evidence for the Reversa Challenges Research

Outputs behind the measured numbers in
[the research brief](../../research-2026-10-02-reversa-challenges.md).
The scripts ran on 2 October 2026 against live public sources, so reruns can differ as
sources update. They were removed from the tree on 3 October 2026: they supported the
choice of challenge, no part of the pipeline uses them, and they sat outside every gate.
They remain in git history at commit [`1142700`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence); each name below links there.

| Script | Produces | Inputs |
| --- | --- | --- |
| [`scan.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence/scan.py) | `hist/<leg>_<type>.json` | Congreso initiative search endpoint, legislatures V-XV |
| [`experiment.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence/experiment.py) | Leave-one-legislature-out AUC and Brier for the baseline rule, logistic regression and gradient boosting | Output of `scan.py` |
| [`explain.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence/explain.py) | Feature weights and subgroup pass rates | Output of `scan.py` |
| [`timing.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence/timing.py) | Filing-to-BOE days (`timing.txt`) | Output of `scan.py`; downloads the BOE API law list on first run |
| [`agreement.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence/agreement.py) | Group agreement with PSOE (`coalition-agreement.txt`) | `attic/congreso-api` session files |
| [`lobbyplag_example.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence/lobbyplag_example.py) | GDPR Article 26(1): verified copies of Amazon's paper versus lookalikes (`lobbyplag-example.txt`) | LobbyPlag data, downloaded on first run |
| [`c01_check.py`](https://github.com/lensabillion/reversa-madrid-open/blob/114270050273783490dba8c7527bd9d9e270fd7e/docs/research/reversa-2026-10/evidence/c01_check.py) | Reproduction of the brief's 12 July 2022 returns and abnormal returns | yfinance |

`base-rates.txt` holds the per-legislature pass rates.
To rerun them, copy the scripts from that commit into a scratch directory, run `scan.py`
first (it writes `./hist/`), then the others from the same directory with
`uv run --no-project --with scikit-learn --with numpy --with yfinance --with pandas python <script>`.
`explain.py` executes the feature-construction part of `experiment.py`, so keep them
together.
