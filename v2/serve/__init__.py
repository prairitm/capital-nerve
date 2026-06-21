"""FastAPI serving layer over the Capital Nerve v2 SQLite store.

This package reads `capital_nerve.db` (produced by the v2 notebook pipeline) and
exposes the HTTP surface the `v1/frontend` React app expects. It does not modify
any existing v2 module or the notebook — the notebook remains the source of
truth for ingestion.
"""
