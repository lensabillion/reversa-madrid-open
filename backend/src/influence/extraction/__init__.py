"""Extraction layer: fetch public sources, cache and store raw responses, keep provenance.

The pipeline reconstructs one chain: actor to ask to amendment to final article. The
modules here do the fetching and the on-disk bookkeeping that every collector in
`services/collect.py` relies on; the typed records they write live in `schemas/atlas.py`.
Design rules, taken from `docs/explainer/Influence Atlas — Data Extraction Playbook.pdf`
and binding on every module in this package:

1. Raw before parsed. Fetches write the untouched response to disk; parsers read files.
2. Cache every request by SHA-256 of method, URL and body, so a repeat never leaves.
3. Manifest-driven. One procedure identifier resolves into a run manifest that the
   collect command publishes last; downstream code reads it.
4. Fail soft. A missing source is recorded absent and the run continues.
5. Provenance on every record: source URL, fetch timestamp and extraction method.
"""
