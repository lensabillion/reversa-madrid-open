# Progress log

## 2026-10-03 10:45 source verification
- Have Your Say: `GET https://ec.europa.eu/info/law/better-regulation/api/allFeedback?publicationId=24212003&page=0&size=N`
  with `Accept: application/json` returns JSON (verified; attachments listed with ids,
  download base `.../api/download/`). Without the Accept header it returns an HTML shell.
- Parltrack: `ep_amendments.json.zst` (120 MB), `ep_dossiers.json.zst` (55 MB) reachable.
- Cellar CELEX endpoint returns the AI Act XHTML (200, 1.26 MB).
- EUR-Lex HTML pages return 202 (anti-bot); use Cellar instead.
- Not verified yet: HowTheyVote API (301), OEIL (307), Transparency Register, LobbyFacts.
- Blockers: `ANTHROPIC_API_KEY` not set; `prompts/verifier.md` not yet provided.
