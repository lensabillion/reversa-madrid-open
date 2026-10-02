---
type: is
id: is-01m3yyx1n9n5n7b2bm03wddfvd
title: "R1: Audit LobbyPlag negative-label semantics before treating them as ground truth"
kind: task
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:22.824Z
updated_at: 2026-10-02T18:44:22.824Z
---
High. attic/prototype-2026-10-02/influence/practice.py:41-46 classifies processing.checked>0 and processing.verified==0 as negative. All 100 resulting negatives have top-level checked=false; 95 have only one crowd check and five have two. Upstream readme defines checked as checking process complete. Calling these gold-standard reviewed rejections is unsupported. Verify the crowd workflow, document weak-label status, and evaluate sensitivity or obtain adjudicated public practice negatives. Do not relabel hidden-test inputs.
