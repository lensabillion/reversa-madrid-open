---
type: is
id: is-01m3yxjrzde6r6gw3jfr2e85bz
title: "Part 1 · Collect: influence collect <procedure> downloads and normalizes one law's public record"
kind: feature
status: in_progress
priority: 0
version: 9
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
updated_at: 2026-10-03T09:43:36.692Z
started_at: 2026-10-02T18:21:17.985Z
---
CLI: influence load <law>. Sources: Have Your Say API (feedback + attachment PDFs as text), Parltrack committee amendments dump, Publications Office (CELLAR) texts of Parliament's position and the final act. Output under data/laws/<law>/ as JSONL + text with provenance. Start with the AI Act (2021/0106(COD)).

## Notes

2026-10-03: branch feat/law-loader (one WIP commit ed6085a, pins only, no code) deleted with the owner's approval; pypdf already on main (#11). The loader is rebuilt fresh from main inside plan step 4 (rev-e5xh), scoped to what adoption labels and ID inputs need. Verified source facts kept: HYS allFeedback?publicationId=14488 has 304 items, 102 pages at size 3, fields id/dateFeedback/feedback/language/userType/country/companySize/organization/trNumber/attachments[id,fileName,documentId]/firstName/surname (drop names: personal data); attachments via /api/download/<documentId> (PDF). Parltrack ep_amendments.json.zst: 4,852 AI Act records stream in 2.3 s with stdlib compression.zstd; fields src, peid, reference, date, committee[list], seq, id, orig_lang, old[lines], new[lines], authors (leading spaces), meps[int], location[[...]], justification (333). CELLAR: http://publications.europa.eu/resource/celex/<celex> with Accept application/xhtml+xml answers 303 to the cellar copy; 52023AP0236 = 2.7 MB, 32024R1689 = 1.26 MB.

2026-10-03, Atlas re-plan (rev-sz6q): retargeted to Atlas part 1 for ANY procedure number since 2019, not one law. Output per law under data/laws/<procedure>/: committee + plenary amendments with old/new text and the extracted change (Parltrack), consultation feedback and attachment PDFs split into passages (HYS brpapi), Commission proposal, EP position and final act (CELLAR), with source URL, retrieval date and SHA-256 per record. Must work from a procedure number alone (any-law rule) and be resumable and cached. The verified facts above still apply.
