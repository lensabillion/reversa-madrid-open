---
type: is
id: is-01m40sheeakgp417re626kget2
title: "Setup command: download the Parltrack dumps and the register export, build the Have Your Say index, with provenance"
kind: task
status: in_progress
priority: 1
version: 2
delegate: claude-code@vm
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T11:49:08.681Z
updated_at: 2026-10-03T12:24:31.286Z
started_at: 2026-10-03T12:24:31.285Z
---
Part 1 (collect). influence collect (PR #34) requires data/raw/parltrack/{ep_dossiers,ep_amendments,ep_plenary_amendments,ep_meps}.json.zst and data/raw/registry/register.xml, and reads data/catalog/hys-index.jsonl when present (else a labelled title search). No command creates them: Agent 1's laptop downloaded them ad hoc. Add one command (e.g. influence setup / make setup) that downloads the four dumps from https://parltrack.org/dumps/<name> and the register from https://ec.europa.eu/transparencyregister/public/files/ODP/download/XML/latest through extraction.fetching with provenance, and crawls the HYS index with repositories.hys.crawl_index (about 4,128 initiatives, ~35 min uncached, resumable through the cache). Needed for rev-p61s (rerun from a fresh checkout).
