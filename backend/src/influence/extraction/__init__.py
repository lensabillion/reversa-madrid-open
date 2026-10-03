"""Extraction layer: fetch public sources, store raw responses, parse typed tables.

The pipeline reconstructs one chain: actor to ask to amendment to final article. Each
module here serves one hop or resolves the actor behind it. Design rules, taken from
`docs/explainer/Influence Atlas — Data Extraction Playbook.pdf` and binding on every
module in this package:

1. Raw before parsed. Fetches write the untouched response to disk; parsers read files.
2. Cache every request by SHA-256 of method, URL and body, so a repeat never leaves.
3. Manifest-driven. One identifier resolves into a manifest; downstream code reads it.
4. Fail soft. A missing source is recorded absent and the run continues.
5. Provenance on every row: source URL, fetch timestamp and extraction method.
"""
