---
type: is
id: is-01m48q8zpd70nd2dzrpfpn3qy9
title: "Protect main: require pull requests and the nine CI checks before merging"
kind: chore
status: in_progress
priority: 1
version: 3
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T13:43:29.741Z
updated_at: 2026-10-06T13:46:47.897Z
started_at: 2026-10-06T13:44:30.480Z
---
Outside the pipeline (repository settings). main had no branch protection (gh api, 2026-10-06): anyone with push could bypass the nine CI checks. Applied with gh api: pull request required (0 approvals, so the owner can merge their own), the nine check contexts required and up to date with main, admins included, no force pushes, no deletions, conversations resolved.

## Notes

Applied 2026-10-06 with gh api PUT branches/main/protection: strict status checks (nine contexts), PR required with 0 approvals, enforce_admins, no force push, no deletion, conversation resolution. Verified by the API response. Follow-up: add the containers check context once the containers workflow (rev-rd33) is on main.
