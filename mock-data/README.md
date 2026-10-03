# Mock Data

Pipeline output kept in the repository so the explorer can be shown without running the
pipeline (about 20 minutes of downloads for one law). The layout mirrors `data/`, so the
backend serves it unchanged:

```sh
INFLUENCE_DATA_ROOT=mock-data make dev-backend   # API at http://127.0.0.1:8000
make dev-frontend                                # http://localhost:3000/lineage?law=2021-0106-COD
```

| File | Law | Produced by | Run |
| --- | --- | --- | --- |
| `laws/2021-0106-COD/lineage.json` | AI Act, 2021/0106(COD) | `make lineage LAW='AI Act' ARGS='--jev --jev-max-usd 1'` on `main` at `ceb0023` | 589 lexical (word-for-word) and 37 semantic (Jev) origins; Jev judged 3,829 pairs for 0.22 USD |
| `laws/2020-0340-COD/lineage.json` | Data Governance Act, 2020/0340(COD) | `make lineage LAW='2020/0340(COD)' ARGS='--jev'` on this branch at `010ee1d` (10 min 11 s, collect 553 s) | 72 lexical and 10 semantic (Jev) origins; Jev judged 1,014 of 1,043 pairs for 0.07 USD |
| `laws/2020-0361-COD/lineage.json` | Digital Services Act, 2020/0361(COD) | `make lineage LAW='2020/0361(COD)' ARGS='--jev --refresh'`, backend source identical to `main` at `d7de70d` (5 min 0 s, asks stage 295 s) | 300 lexical and 61 semantic (Jev) origins; Jev judged 2,197 of 2,483 pairs for 0.13 USD |
| `laws/2020-0374-COD/lineage.json` | Digital Markets Act, 2020/0374(COD) | `make lineage LAW='2020/0374(COD)' ARGS='--jev --refresh'`, backend source identical to `main` at `d7de70d` (1 min 38 s, asks stage 94 s) | 158 lexical and 37 semantic (Jev) origins; Jev judged 1,110 of 1,212 pairs for 0.07 USD |
| `laws/2022-0047-COD/lineage.json` | Data Act, 2022/0047(COD) | `make lineage LAW='2022/0047(COD)' ARGS='--jev --refresh'`, backend source identical to `main` at `d7de70d` (4 min 1 s, asks stage 237 s) | 97 lexical and 34 semantic (Jev) origins; Jev judged 1,109 of 1,202 pairs for 0.07 USD |

Generated, not edited: every link, count and ranking comes from the pipeline. The file is
a snapshot, not a source of truth; rerun the command to refresh it. All content is public
(Parltrack, EUR-Lex, Have Your Say). The Have Your Say index was not built for the AI Act
and Data Governance Act runs, so their consultations were found by title search (the
view's coverage rows say so); the other three runs found theirs through the index. "Backend
source identical" means the `src-` hash the run manifest records for `backend/src/influence/`
equals that commit's.
