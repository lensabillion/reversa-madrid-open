---
type: is
id: is-01m3yxjrzde6r6gw3jfr2e85bz
title: "Part 1 · Collect: influence collect <procedure> downloads and normalizes one law's public record"
kind: feature
status: in_progress
priority: 0
version: 15
delegate: claude-code@vm
labels: []
dependencies:
  - type: blocks
    target: is-01m3z9e7eesds3s8v38tswk2p6
  - type: blocks
    target: is-01m40fgh7rr8spaqfeat0v6qzm
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T18:21:17.677Z
updated_at: 2026-10-03T12:26:56.925Z
started_at: 2026-10-02T18:21:17.985Z
---
CLI: influence load <law>. Sources: Have Your Say API (feedback + attachment PDFs as text), Parltrack committee amendments dump, Publications Office (CELLAR) texts of Parliament's position and the final act. Output under data/laws/<law>/ as JSONL + text with provenance. Start with the AI Act (2021/0106(COD)).

## Notes

2026-10-03: branch feat/law-loader (one WIP commit ed6085a, pins only, no code) deleted with the owner's approval; pypdf already on main (#11). The loader is rebuilt fresh from main inside plan step 4 (rev-e5xh), scoped to what adoption labels and ID inputs need. Verified source facts kept: HYS allFeedback?publicationId=14488 has 304 items, 102 pages at size 3, fields id/dateFeedback/feedback/language/userType/country/companySize/organization/trNumber/attachments[id,fileName,documentId]/firstName/surname (drop names: personal data); attachments via /api/download/<documentId> (PDF). Parltrack ep_amendments.json.zst: 4,852 AI Act records stream in 2.3 s with stdlib compression.zstd; fields src, peid, reference, date, committee[list], seq, id, orig_lang, old[lines], new[lines], authors (leading spaces), meps[int], location[[...]], justification (333). CELLAR: http://publications.europa.eu/resource/celex/<celex> with Accept application/xhtml+xml answers 303 to the cellar copy; 52023AP0236 = 2.7 MB, 32024R1689 = 1.26 MB.

2026-10-03, Atlas re-plan (rev-sz6q): retargeted to Atlas part 1 for ANY procedure number since 2019, not one law. Output per law under data/laws/<procedure>/: committee + plenary amendments with old/new text and the extracted change (Parltrack), consultation feedback and attachment PDFs split into passages (HYS brpapi), Commission proposal, EP position and final act (CELLAR), with source URL, retrieval date and SHA-256 per record. Must work from a procedure number alone (any-law rule) and be resumable and cached. The verified facts above still apply.

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): Merged: PR #25 (shared contracts schemas/atlas.py, schema atlas-1, fixtures; CI 9/9 green) and PR #26 (feat/collect-law, merged 13:08): services/law_query.py, StageStore in extraction/records.py, repositories/parltrack.py, repositories/cellar.py, repositories/hys.py + services/passages.py, repositories/register.py + services/actors.py. Reported by Agent 1 on real data: committee amendments AI Act 4,852, DSA 5,901, EHDS 2,458 (match research); CELLAR AI Act 52021PC0206 -> 32024R1689, final act 113 articles. Have Your Say real-data check NOT reported. NOT done: services/collect.py and `influence collect <query>` (handoff steps 3-4), Parliament position text, gate 1 on real sources with timings. Open owner decisions (docs/agents/agent-1-handoff.md): insertions without `old` -> null or ""; Amendment.document_id joins no SourceDocument; the Europe/European/EU name rule; parliament_position source. Claim released: claude-code@vm stopped at the owner's request; per the handoff the owner agreed Agent 1's session takes this bead over. Beads rev-k9rm, rev-lh4f, rev-ifao named in the handoff are not in the shared tracker (not synced from Agent 1's laptop).

2026-10-03 14:05 CEST: PR https://github.com/lensabillion/reversa-madrid-open/pull/34 (branch claude/eloquent-allen-jbxbmy, commits 8891f3d, 2f246f6): services/collect.py + influence collect / make collect LAW=. Stages texts (CELLAR), amendments (Parltrack + MEPs), asks (HYS by COM, passages, register actors), law (LawRecord with 10 typed coverage rows); StageStore reuse keyed on inputs + source_revision; RunManifest published last; stop rule (no amendments and no asks). Verified offline: 41 tests; make check-backend 636 passed, 100% branch coverage (3,947 statements, 994 branches); check-docs 6/6; check-scripts. NOT verified: real-data run (cloud session network blocks EU hosts) - run make collect LAW='2021/0106(COD)' on a laptop and record counts and cached/uncached timings before closing. Keep open until merged and the real-data gate-1 numbers are recorded.

2026-10-03 13:51 CEST: PR #34 merged by the owner (all 9 CI checks green on 2f246f6, backend tests completed 11:49:40Z). Open item before closing: the real-data gate-1 run on a laptop with the data - make collect LAW='2021/0106(COD)' - recording counts against the research (4,852 committee amendments; 304 HYS items, 259 with attachments) and cached/uncached timings with hardware; then a second law (DSA 2020/0361(COD)) with no code change. Setup command tracked in rev-6c1o.

2026-10-03 14:15 CEST: PR #45 merged: amendments now cite their Parltrack dump SourceDocument (graph join fixed); MEPs missing from the MEP dump get placeholder actors (counts.meps_not_in_dump). Still open until the real-data run of make collect LAW='2021/0106(COD)' on a laptop, with counts and timings recorded.

2026-10-03 Agent 2, real run of the collect stage on the AI Act: 18.5 s from cache (39.4 s first time), 376 proposal / 712 final-act provisions, 4852 committee and 808 plenary amendments, 437 asks (352 attachments skipped), 583 actors. Two crashes found and fixed in PR #47: JSON Lines readers used str.splitlines() which splits at U+2028 (one submission holds a raw U+2028), and an amendment over 800 tokens stopped retrieval for the whole law. Whole atlas command: 2 min 10 s. CELLAR article-kind counts (19 final, 22 proposal) differ from the handoff's (113, 85); totals match, probably a classification difference, unchecked.
