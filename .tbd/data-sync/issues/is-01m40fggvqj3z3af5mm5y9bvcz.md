---
type: is
id: is-01m40fggvqj3z3af5mm5y9bvcz
title: "D6: choose an open licence and make the repository public, after checking history for anything unpublishable"
kind: task
status: closed
priority: 1
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:52.630Z
updated_at: 2026-10-06T14:20:11.979Z
started_at: 2026-10-06T13:43:29.125Z
closed_at: 2026-10-06T14:20:11.979Z
close_reason: "PR #87 merged by the owner 2026-10-06 14:18 UTC: LICENSE (Apache-2.0), README licence section, D6 decided, skill step 6 updated; all nine checks green. The remote branch ¨transfer¨ (Written Report (29).pdf) still needs a publish-or-delete decision; noted on rev-i2dl's cleanup follow-ups."
resolution: null
duplicate_of: null
---
Brief rule: code in a public repo with an open licence. The repo is PRIVATE with no LICENSE (gh, 2026-10-03). Owner decision, outward-facing. Proposed: Apache-2.0 for code; ODbL for graph data derived from Parltrack (ODbL); CC BY 4.0 for the report. Before publishing: scan git history for secrets and personal data; data/ and attic/ were never committed.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/87 opened 2026-10-06: LICENSE (Apache-2.0, verbatim, sha256 cfc7749b…), README licence section, D6 row decided, skill step 6 updated. History scan for keys/.env/data: none found. The remote branch ¨transfer¨ holds docs/brief/Written Report (29).pdf (1.5 MB) off main; decide whether it may be public, then delete the branch.
