# Render Deploy Branch

This branch is `main` plus the finished lineage views that the hosted backend serves.
Render deploys the backend from it; `main` never holds data (`data/` is not committed).

`views/laws/<slug>/lineage.json` is the unedited output of `make lineage LAW='...'`, copied
from a local run. The backend reads it through `INFLUENCE_DATA_ROOT`, set on Render to
`/opt/render/project/src/deploy/views`.

| View | Built from | Command |
| --- | --- | --- |
| `2021-0106-COD` (AI Act) | `main` at `70ef667`, run `20261003T154842Z` | `influence lineage "AI Act"` |

To add a law: run `make lineage LAW='...'` locally, copy its `lineage.json` here under
`views/laws/<slug>/`, commit and push; Render redeploys this branch.
