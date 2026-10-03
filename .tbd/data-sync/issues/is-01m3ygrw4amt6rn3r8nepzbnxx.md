---
type: is
id: is-01m3ygrw4amt6rn3r8nepzbnxx
title: Propose the architecture and tool choices, and agree them with the user
kind: task
status: closed
priority: 1
version: 7
delegate: codex@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m3ygrwb65kmfggfxnx6dtsys
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T14:37:26.025Z
updated_at: 2026-10-03T08:48:16.837Z
started_at: 2026-10-02T18:26:08.218Z
closed_at: 2026-10-03T08:48:16.837Z
close_reason: The seven-part architecture was agreed on 2026-10-02 (Decisions table). The organizers replaced the brief on 2026-10-03; re-planning continues in rev-sz6q.
resolution: null
duplicate_of: null
---
No build code until the user agrees the architecture and tools.

## Notes

Architecture assessment for Challenge 03 — 2 October 2026

Scope: the proposed new architecture in docs/explainer/influence-graph-primer.md sections 6 and 11, plus the current law-loader task rev-pjk2. The user is not using the attic prototype. Its implementation defects are not prerequisites for implementing this new design. This is an engineering recommendation, not a record of user approval of every proposed choice.

Verdict: retain Python/FastAPI, Next.js/Tailwind, public-source loading, change-aware scoring, saved evidence, and a graph derived from results. Improve the dependency structure and delivery order to maximize the chance of a complete, accurate hackathon submission. Astra independently agreed with this assessment.

RAG and storage: this is retrieval-assisted evidence scoring, not primarily a question-answering chatbot. For each of 60 supplied amendment/submission pairs, retrieve relevant passages within that submission, compare them with the amendment, and produce a score and evidence. Semantic retrieval is optional. No vector database is needed for this scope. Keep normalized text and provenance in local JSONL, and optional embeddings in local numeric arrays. Add a vector database only if a later product needs repeated indexed search across a large changing corpus; it is not a prerequisite for embeddings or retrieval.

Recommended flow:
Input adapters and local cache -> normalized records -> passage shortlist plus before/after legal context -> lexical and semantic assessment -> pair score and evidence -> pairs.csv.
Normalized proposal records plus permitted historical evidence -> separate adoption scorer -> proposals.csv.
Saved evidence from both paths -> FastAPI -> Next.js tracer and small influence graph.
The batch CLI is independent of FastAPI, the UI, and graph layout. Adoption can use matching evidence but must work before the graph is finished.

What to keep: the loader's common format and provenance; comparing legal changes instead of generic topic overlap; a simple scoring model if representative labels support it; explicit evaluation; one evidence record powering both exports and the demo. Keep the already chosen web stack rather than reopening that choice.

What to change:
1. Build input/output contracts and both CSV writers first, using fixtures only to test plumbing. Preserve input IDs and validate exact row counts, unique IDs and finite scores in [0,1]. Fixtures do not prove predictive accuracy.
2. Search within supplied submissions first. Corpus-wide source discovery, universal organization enrichment and full-law graph construction are optional extensions.
3. Preserve original clause, amended clause, insertion/deletion locations, surrounding context and source/page references. Do not reduce the semantic judge's input to isolated changed words.
4. Retrieve a few candidate passages. Assess same requested operation, affected actor, negation, exceptions and quantities. Validate that evidence quotations actually occur in the source. Avoid inventing certainty from model self-confidence.
5. Benchmark one available semantic judge against a lexical baseline. Developer delegation to Astra/Sol does not itself provide runtime API access. Choose the runtime judge after checking credentials, measured quality and latency. A complex model router is not an initial requirement for 60 pairs.
6. Make adoption a parallel mandatory deliverable. Resolve prediction date and permitted evidence through rev-qvmx. Historical final-law text can supply labels; its use as prediction input requires an explicit compatible challenge rule. Graph completion must not block this scorer.
7. Build an amendment tracer before graph polish: highlight the matching passages and legal change, explain the score, then show connected organizations/MEPs. Show heard versus final survival only where supported. Avoid universal win-rate claims from incomplete coverage.
8. Require a timed 60-pair/20-proposal rehearsal before adding breadth. Exercise text and ID inputs, cache behavior and an unavailable optional service. Save partial progress and publish only complete validated outputs. Choose and measure a runtime target with substantial margin inside the one-hour window.

Suggested delivery milestones for Saturday 3 October, Madrid time: by midday one real example through each scorer and validated exports; by mid-afternoon a complete rehearsal; by 17:00 freeze a reliable baseline; 17:00-18:30 evaluate targeted improvements and rehearse the demo; at 19:00 run the hidden inputs and validate well before the 20:00 deadline. These are proposed gates, not estimates of completed work. Observe organizer rules about advance preparation.

Team allocation: one owner for ingestion/contracts/batch reliability, one for pair scoring/evaluation, one for adoption plus tracer. Graph polish follows shared evidence contracts. Use Astra for high-engineering reasoning and review, Sol for mechanical implementation; keep tbd current.

Priority judgement: target the hidden-test deliverables first (60% of the event score), maintain all three challenge steps for the difficulty component, and tell one clear five-minute evidence-led demo story. No architecture guarantees a win; this plan reduces avoidable incompleteness and puts effort into the evaluated behavior.
