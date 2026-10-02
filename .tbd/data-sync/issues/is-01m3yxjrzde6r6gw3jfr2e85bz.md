---
type: is
id: is-01m3yxjrzde6r6gw3jfr2e85bz
title: "Law loader: fetch one law's submissions, amendments, Parliament position and final act into one clean format"
kind: feature
status: open
priority: 1
version: 4
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T18:21:17.677Z
updated_at: 2026-10-02T21:49:04.893Z
started_at: 2026-10-02T18:21:17.985Z
---
CLI: influence load <law>. Sources: Have Your Say API (feedback + attachment PDFs as text), Parltrack committee amendments dump, Publications Office (CELLAR) texts of Parliament's position and the final act. Output under data/laws/<law>/ as JSONL + text with provenance. Start with the AI Act (2021/0106(COD)).

## Notes

2026-10-03: branch feat/law-loader (one WIP commit ed6085a, pins only, no code) deleted with the owner's approval; pypdf already on main (#11). The loader is rebuilt fresh from main inside plan step 4 (rev-e5xh), scoped to what adoption labels and ID inputs need. Verified source facts kept: HYS allFeedback?publicationId=14488 has 304 items, 102 pages at size 3, fields id/dateFeedback/feedback/language/userType/country/companySize/organization/trNumber/attachments[id,fileName,documentId]/firstName/surname (drop names: personal data); attachments via /api/download/<documentId> (PDF). Parltrack ep_amendments.json.zst: 4,852 AI Act records stream in 2.3 s with stdlib compression.zstd; fields src, peid, reference, date, committee[list], seq, id, orig_lang, old[lines], new[lines], authors (leading spaces), meps[int], location[[...]], justification (333). CELLAR: http://publications.europa.eu/resource/celex/<celex> with Accept application/xhtml+xml answers 303 to the cellar copy; 52023AP0236 = 2.7 MB, 32024R1689 = 1.26 MB.
