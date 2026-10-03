---
type: is
id: is-01m3yyx2qx3gwyytzfqz9vxnpc
title: "R7: Fix passage retrieval repetition bias and preserve candidate alternatives"
kind: task
status: open
priority: 1
version: 3
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:23.932Z
updated_at: 2026-10-03T11:23:06.715Z
---
High. text.py:99-101 counts repeated matching tokens as separate hits against a set denominator. With base controller shall protect personal data, a window containing controller repeated 30 times outranks a sentence containing the whole base plus securely. Diffing arbitrary prose against a legal clause also turns explanation into alleged edits. Bound term contributions, retain source paragraph boundaries, retrieve several candidates and evaluate evidence-span recall before the pair scorer. Additional medium defect: features.py:104 truncates alignment at 400 tokens but normalizes by full input; identical 800-token inputs score .5.

## Notes

2026-10-03, Atlas re-plan (rev-sz6q): applies to Atlas part 3 (find candidates) and the passage selection inside it.

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): Retrieval landed in PR #27 (services/retrieval.py); repetition bias and alternative preservation not addressed there yet. Two passage splitters now exist on main (retrieval.split_passages and services/passages.py).
