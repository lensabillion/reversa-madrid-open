# Evidence for the Reversa Challenges Research

Scripts and outputs behind the measured numbers in
[the research brief](../../research-2026-10-02-reversa-challenges.md).
They ran on 2 October 2026 against live public sources, so reruns can differ as sources update.

| Script | Produces | Inputs |
| --- | --- | --- |
| `scan.py` | `hist/<leg>_<type>.json` | Congreso initiative search endpoint, legislatures V-XV |
| `experiment.py` | Leave-one-legislature-out AUC and Brier for the baseline rule, logistic regression and gradient boosting | Output of `scan.py` |
| `explain.py` | Feature weights and subgroup pass rates | Output of `scan.py` |
| `timing.py` | Filing-to-BOE days (`timing.txt`) | Output of `scan.py`; downloads the BOE API law list on first run |
| `agreement.py` | Group agreement with PSOE (`coalition-agreement.txt`) | `attic/congreso-api` session files |
| `lobbyplag_example.py` | GDPR Article 26(1): verified copies of Amazon's paper versus lookalikes (`lobbyplag-example.txt`) | LobbyPlag data, downloaded on first run |
| `c01_check.py` | Reproduction of the brief's 12 July 2022 returns and abnormal returns | yfinance |

`base-rates.txt` holds the per-legislature pass rates.
Copy the scripts into a scratch directory, run `scan.py` first (it writes `./hist/`), then
the others from the same directory with
`uv run --no-project --with scikit-learn --with numpy --with yfinance --with pandas python <script>`.
`explain.py` executes the feature-construction part of `experiment.py`, so keep them
together.
