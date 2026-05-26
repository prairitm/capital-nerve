# scripts/seed_nifty50_companies

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Bulk-create `Company` rows (and matching NSE `Security` rows) from
`backend/var/nse_nifty50.json` or any file with the same shape. Used to
bootstrap the issuer catalog before IR discovery / ingestion.

## Source

- Path: `backend/app/scripts/seed_nifty50_companies.py`
- Entry: `python -m app.scripts.seed_nifty50_companies [options]`
- Layer: backend-script

## CLI surface

- `--input` / `-i` — JSON file path (default:
  `backend/var/nse_nifty50.json`).
- `--dry-run` — print proposed creates without writing to the DB; also
  passes `--dry-run` to chained commands.
- `--resolve-bse` — after seeding, run
  `python -m app.scripts.resolve_bse_codes --auto-accept`.
- `--ingest` — after seeding (and optional BSE resolve), run
  `bulk_ingest --symbols-file <input>` for the same JSON file.
- `--ingest-only` — skip seeding and BSE resolve; only bulk-ingest symbols
  from the JSON file (for companies already in the DB).
- Period flags (required with `--ingest` / `--ingest-only`): exactly one of
  `--from` + `--to`, or `--last-quarters N`.
- `--no-agent-fallback` / `--nse-scraper` — forwarded to `bulk_ingest`.
- `--log-level` — Python logging level.

Standalone bulk ingest for the same file:

```bash
python -m app.scripts.bulk_ingest --symbols-file var/nse_nifty50.json --last-quarters 4
```

Each JSON object requires `legal_name`, `nse_symbol`, and `sector`.
`nse_symbol` is normalised to uppercase. Rows whose symbol already exists
in `companies.nse_symbol` are skipped. Unknown `sector` values create a
new `Sector` row (same behaviour as `POST /admin/companies`).

## Contract

- Input: JSON array of `{ "legal_name": str, "nse_symbol": str, "sector": str }`.
- Output: stdout summary (`created` / `skipped` counts).
- Exit `0` on success; exit `2` on invalid or empty JSON.

## Dependencies

- May import: `typer`, `pydantic`, `sqlalchemy`, `app.db.session`,
  `app.models.master`, `app.core.env.bootstrap_cli_env`.
- Must not import: `app.routers.*`, FastAPI, pipeline or IR-discovery
  packages.

## Verification checklist

- [ ] Re-running after a successful import reports only skips and
      creates 0 new rows.
- [ ] `--dry-run` prints the same proposed actions twice (no DB writes).
- [ ] Invalid JSON or a missing required field exits with code 2.
- [ ] Each new company has an active NSE `Security` with the same
      symbol as `nse_symbol`.
