# The Influence Atlas: plan

Goal: public map of who shapes EU law (actor -> ask -> amendment -> final article) for any
EU law since 2019. Judged on real links (precision over recall), any-law CLI, insight,
report, ambition. Demo 2026-10-03 19:30.

## Pilot law: AI Act (2021/0106(COD), CELEX 32024R1689)
Verified 2026-10-03 (see PROGRESS.md): consultation feedback + attachments via the Have
Your Say JSON API (publicationId 24212003, COM(2021)206); amendments in the Parltrack
`ep_amendments` dump (120 MB); procedure metadata in `ep_dossiers` (55 MB); final text via
Cellar (`publications.europa.eu/resource/celex/32024R1689`, XHTML, 1.2 MB).

## Pipeline (idempotent, cached, provenance on every row)
1 resolve law -> 2 ingest/normalise -> 3 delta extraction -> 4 hybrid retrieval ->
5 evidence features -> 6 LLM verifier (needs ANTHROPIC_API_KEY, prompts/verifier.md) ->
7 edge table -> 8 amendment<->final alignment -> 9 win metrics -> 10 forecast -> 11 outputs
(graph.json, static web page, auto report).

## Checkpoints
13:00 slice, 15:30 any-law CLI, 17:30 insight+forecast, 18:30 report, 18:45 freeze.
