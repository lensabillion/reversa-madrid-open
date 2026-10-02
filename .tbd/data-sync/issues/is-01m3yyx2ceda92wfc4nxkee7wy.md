---
type: is
id: is-01m3yyx2ceda92wfc4nxkee7wy
title: "R5: Correct the claimed difference from LobbyPlag using its actual matcher source"
kind: task
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:23.566Z
updated_at: 2026-10-02T18:44:23.566Z
---
High. docs/research/influence-2026-10/existing-systems.yaml:14-28 and primer:384 claim LobbyPlag compares whole old/new texts. Public upstream bin/plags.js at revision 6880188eb528b5eb00cf7efdadfccdd3d5e73795 explicitly compares proposal.text.ins against amendment.text[0].ins and then del against del. Its candidate threshold is >0.4. Correct the comparator description and novelty argument; do not attribute the improvement simply to introducing change-only comparisons. Reproduced stored baseline metrics do not validate the incorrect explanation.
