---
type: is
id: is-01m3z9dqqvc07bp91ha0m517k7
title: "Audit PRs #10-#14 against the seven-part architecture and the four project rules"
kind: task
status: closed
priority: 1
version: 2
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T21:48:15.482Z
updated_at: 2026-10-02T21:48:31.125Z
closed_at: 2026-10-02T21:48:31.125Z
close_reason: |
  Audit done 2026-10-02 23:30 CEST; owner agreed the plan at 23:55.
  Evidence: make check on a fresh clone of main ae35edb exited 0 in 18 s (110 backend tests, 100% branch coverage of 475 statements and 104 branches, 38 frontend tests, build, audits clean); CI green on ae35edb. Gate probes untouched by #10-#14; all lock pins at least 14 days old (newest idna 3.20, 2026-09-17); PR descriptions follow the template; beads closed with evidence except rev-6i5t (now closed).
  Findings: no one-command 19:00 path; parts 4 (combine, pairs.csv) and 6 (adoption, proposals.csv) missing; no practice harness on main; scorer caps texts at 800 tokens and has no passage finder (part 2); the graph (part 5) is built from LobbyPlag historical labels, not our scores; demo built before the CSV path; no property-based tests; #10-#14 each merged 4-29 minutes after opening with no GitHub review.
  Measurement (scratchpad, seed 0, 2,000 draws of 30 verified vs 30 crowd-rejected LobbyPlag pairs, clean edits): main lexical scorer P@20 0.977, recall@0.5 0.798, AUC 0.855; LobbyPlag stored match P@20 0.860, AUC 0.810 (reproduces the primer). Caveats: weak negatives (R1), one law, English, mostly verbatim copies.
  Agreed plan: 0 housekeeping; 1 submission command writing pairs.csv; 2 practice harness on main; 3 passage finder; 4 adoption baseline and proposals.csv; 5 better signals one per PR with harness evidence; 6 demo realignment (graph and scoreboard from our scores); 7 docs refresh. Owner decisions: D3 decided (attic predates the architecture, not built on; PR #16); TypeScript 7 and the next 16.3.6 exception approved.
resolution: null
duplicate_of: null
---
Handoff attic/handoff-2026-10-02.md, step 'audit and realign'. Map main's modules to architecture parts, check #10-#14 against the four rules, run make check from a clean clone, report and agree a realignment plan with the owner.
