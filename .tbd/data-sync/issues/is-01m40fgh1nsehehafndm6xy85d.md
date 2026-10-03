---
type: is
id: is-01m40fgh1nsehehafndm6xy85d
title: "D1: decide the language-model judge for part 4 (none, local open model, Claude, Jev) on practice-loop evidence"
kind: task
status: in_progress
priority: 1
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:52.821Z
updated_at: 2026-10-03T13:31:17.160Z
started_at: 2026-10-03T12:01:03.578Z
---
Open decision D1. Under the Atlas brief the judge runs on thousands of candidates, not 60 pairs, so cost and speed matter; a local model needs no key and no approval to send text. Measure each option on LobbyPlag folds and the blind audit before adopting.

## Notes

Local-model evaluation completed in merged PR48: DeBERTa17/24syntheticdiagnostics; no fittedjudge activated. Currentmainrules3 keepsproseunconfirmed; actualAIActCLI produced0published/859unconfirmed. Owner now supplied TYPESAFE_API_KEY in primarycheckout backend/.env (Gitignored/untracked). Readonly GET https://api.typesafe.ai/v1/models authenticated HTTP200 on3October2026; no inference calls and no secret output/copies. TypeSafe docs currentlylist pinnedjev-1.13.0 atUSD0.042/millioninputtokens, outputfree. Prepare semanticjudge evaluation with24existinglegaldiagnostics plus representative realAIActprose, knownshareddefinitionfailures and explicitmodalcases. User earlier required no paidAPI; asyncquestion pending for confirmedfreecredits-only vsUSD1cap. Addingkey authorizes relevantauthentication but budgetnotyetclarified. Do not start billedinference untilanswer or verifiedfreecredits. No publicationthresholdapproved; evaluationmustkeepmodeloutputs separatefromlabels and exactspan/dateguards mandatory.
