---
type: is
id: is-01m3zaf8nvtv026dc5mwqwg25w
title: "Remove research code outside the pipeline: Qwen experiment runtime and challenge-choice evidence scripts"
kind: chore
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T22:06:34.170Z
updated_at: 2026-10-02T22:06:34.170Z
---
Owner-approved 2026-10-03. Remove backend/evaluation/runtime (run_qwen.py, pyproject.toml, 55-package uv.lock audited by every make check) with its Makefile targets and AGENTS.md rows, and the 7 Python scripts in docs/research/reversa-2026-10/evidence (outside every gate, 148 Ruff findings, R12 rev-4sh8). Keep generated results and text outputs; point their documentation at the code in git history by permalink.
