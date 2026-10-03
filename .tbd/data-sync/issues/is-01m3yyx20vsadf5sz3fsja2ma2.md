---
type: is
id: is-01m3yyx20vsadf5sz3fsja2ma2
title: "R3: Replace the synthetic paper benchmark with a real document ingestion evaluation"
kind: task
status: open
priority: 1
version: 3
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:23.194Z
updated_at: 2026-10-03T11:23:09.916Z
---
High. practice.py:53-61 constructs paper mode by joining previously extracted proposal new-text fields. It never loads original full PDFs, old-text columns, explanatory prose, OCR, or arbitrary document layout. facts.yaml:159 and primer:428 call this the whole lobby paper. Rename current mode as reconstructed proposal text and run a separate benchmark from raw public source documents, with evidence spans and retrieval recall.

## Notes

2026-10-03, Atlas re-plan (rev-sz6q): applies to Atlas parts 1 and 3: measure on real Have Your Say PDFs from 2019+ laws whether passage extraction keeps the evidence.

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): Have Your Say connector and passage splitter merged in PR #26; the real-PDF extraction check on Have Your Say submissions is not yet reported.
