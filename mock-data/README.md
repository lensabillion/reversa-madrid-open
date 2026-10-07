# Mock Data

Pipeline output kept in the repository so the explorer can be shown without running the
pipeline (about 20 minutes of downloads for one law). The layout mirrors `data/`, so the
backend serves it unchanged:

```sh
INFLUENCE_DATA_ROOT="$PWD/mock-data" make dev-backend   # API at http://127.0.0.1:8000
make dev-frontend                                # http://localhost:3000/lineage?law=2021-0106-COD
```

| File | Law | Produced by | Run |
| --- | --- | --- | --- |
| `laws/2021-0106-COD/lineage.json` | AI Act, 2021/0106(COD) | `make lineage LAW='AI Act' ARGS='--jev --jev-max-usd 1'` on `main` at `ceb0023` | 589 lexical (word-for-word) and 37 semantic (Jev) origins; Jev judged 3,829 pairs for 0.22 USD |
| `laws/2020-0340-COD/lineage.json` | Data Governance Act, 2020/0340(COD) | `make lineage LAW='2020/0340(COD)' ARGS='--jev'` on this branch at `010ee1d` (10 min 11 s, collect 553 s) | 72 lexical and 10 semantic (Jev) origins; Jev judged 1,014 of 1,043 pairs for 0.07 USD |

Generated, not edited: every link, count and ranking comes from the pipeline. The file is
a snapshot, not a source of truth; rerun the command to refresh it. All content is public
(Parltrack, EUR-Lex, Have Your Say). The Have Your Say index was not built for this run,
so the consultation was found by title search for both laws (the view's coverage rows say so).
