---
type: is
id: is-01m414dp3b25d0rwt3ks48xc8v
title: "Part 4 · Jev judge on the live atlas path: judge every candidate, publish above the practice-measured cutoff"
kind: feature
status: in_progress
priority: 0
version: 2
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T14:59:19.786Z
updated_at: 2026-10-03T14:59:24.314Z
started_at: 2026-10-03T14:59:24.313Z
---
Owner decision 2026-10-03 (D1): use Jev (TypeSafe jev-1.13.0) as Part 4's judge on the live path, on all top-5 candidates per amendment (~28k on the AI Act, est. $2-4). Reuse PR #63's client (services/jev.py) and its four Noul questions verbatim. Publish when min(actual_request, same_legal_change, 1-shared_background, 1-incompatible) >= 0.67 (cached LobbyPlag practice answers: 57/58, precision 0.983, Wilson lower 0.909), the ask predates the amendment, and the match is not mostly proposal quotation. Cache answers by request hash; parallel calls; dollar cap; failures keep links unconfirmed and are reported. Projection from cached answers on the 941 rules-kept pairs: 22 pass Jev, 16 after masking. Gate 3 needs 20 published + 10 read.
