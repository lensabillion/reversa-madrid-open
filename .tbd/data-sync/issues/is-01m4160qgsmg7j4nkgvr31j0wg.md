---
type: is
id: is-01m4160qgsmg7j4nkgvr31j0wg
title: Parts 5/7 · Rankings inherit amendment outcomes through unconfirmed links, against 'never mixed into rankings'
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3yp5tjt1gsz6s29w5wgs9ep
created_at: 2026-10-03T15:27:12.408Z
updated_at: 2026-10-03T15:27:12.408Z
---
Found 3 Oct while comparing backend and frontend. pipeline.trace picks each ask's origin among published OR unconfirmed links (TRACED_STATUSES); outcomes.trace_outcomes then judges the final act with _request(ask, amendment), so the ask inherits the amendment's survival. On the AI Act view (collect run 20261003T150336Z, rules-3) all 440 final-act outcomes come via amendments reached only by unconfirmed links (0 published), giving 20 partial wins over 18 actor rows on 'See the outcomes'. A change to unpublished candidates alone (rules-4, PR #71) moved them to 8 partial wins over 8 rows. The architecture skill's rule says unconfirmed candidates are 'never mixed into rankings'; the view's limitation sentence documents the behaviour but the UI copy does not say wins come from unconfirmed links. Decision for the owner: trace via published links only (unconfirmed asks traced on their own wording or left unknown), or keep it and label the rankings explicitly.
