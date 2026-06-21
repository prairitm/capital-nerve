# services/pipeline/storage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Persist uploaded source bytes so the pipeline (and any future re-runs) can read
them back. Today the only backend is the local filesystem; the
`LocalStorage` API mirrors S3 semantics so swapping later is a one-file change.

## Source

- Path: `backend/app/services/pipeline/storage.py`
- Layer: backend-service

## Contract

- `LocalStorage.put_bytes(data, suffix=...) -> StoredFile` — content-addressed
  write to `STORAGE_DIR/<hash[:2]>/<hash[2:4]>/<hash><suffix>`. Used for
  uploaded source documents so duplicate uploads naturally dedupe.
- `LocalStorage.put_bytes_at(data, *, path) -> StoredFile` — path-addressed
  write to an arbitrary `STORAGE_DIR/<path>`. Used by `parsing.persist_pages`
  to lay out rendered page PNGs at the predictable
  `page_images/<document_id>/<NNNN>.png` location so the extraction stage
  can load them by `DocumentPage.image_path` without an extra lookup.
- `LocalStorage.open_bytes(storage_path) -> bytes` — reads back either form.
- `LocalStorage.exists(storage_path) -> bool`.
- `get_storage() -> LocalStorage` — the only call site outside this module.

## Dependencies

- May import: `app.core.config.settings`.
- Must not import any pipeline stage, router, or model.

## Patterns (symmetry)

- File names use the sha256 of the contents — so duplicate uploads dedupe.
- Two-level sharding (`hash[:2]/hash[2:4]/`) keeps single directories from
  exploding when ingest scales.
- `storage_path` returned is relative to the storage root so it round-trips
  through `SourceDocument.storage_path` without leaking host filesystem layout.

## Verification checklist

- [ ] `STORAGE_DIR` honoured (env override works).
- [ ] Duplicate `put_bytes` of the same payload does not rewrite the file.
- [ ] `open_bytes` returns identical bytes for previously-stored payloads.
- [ ] No imports from `app.services.pipeline.*` or `app.routers.*`.
