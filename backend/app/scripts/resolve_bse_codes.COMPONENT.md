# scripts/resolve_bse_codes

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Backfill `Company.bse_code` for rows the catalog seed left null. The
seed only loads NSE symbols; BSE-first IR discovery in
[`services/ir_discovery/exchange/discover.py`](../services/ir_discovery/exchange/discover.py)
needs the 6-digit BSE scrip code to call `api.bseindia.com`. Without
this script every issuer falls through to NSE / agent.

## Source

- Path: `backend/app/scripts/resolve_bse_codes.py`
- Entry: `python -m app.scripts.resolve_bse_codes [options]`
- Layer: backend-script

## CLI surface

- `--refresh` — force a fresh download of the BSE master list (else the
  on-disk cache at `var/bse_master/equity.json` is used while it's
  fresher than `BSE_MASTER_TTL_DAYS`).
- `--auto-accept` — accept fuzzy matches above the cutoff without
  prompting. Required for non-interactive runs.
- `--dry-run` — print proposed updates without writing to the DB.
- `--fuzzy-cutoff 0.92` — minimum `SequenceMatcher` ratio (overrides
  the default in `bse_master.lazy_resolve_bse_code`).
- `--symbols RELIANCE,TCS` — restrict resolution to specific NSE
  symbols (default: every `Company.bse_code IS NULL`).

Resolution order per company: ISIN → exact NSE-symbol → fuzzy
`company_name`. Exact methods (`isin`, `nse_symbol`) are always
auto-accepted because they are deterministic; only fuzzy matches
prompt.

## Behaviour

- Idempotent: companies that already have `bse_code` set are skipped.
- A single `db.commit()` at the end means a Ctrl-C mid-run rolls back
  cleanly.
- Exit codes:
  - `0` — finished (including "nothing to do").
  - `2` — BSE master list could not be loaded (network failure and no
    cache).

## Dependencies

- May import: `typer`, `sqlalchemy`, `app.db.session`,
  `app.models.master.Company`,
  `app.services.ir_discovery.exchange.bse_master`,
  `app.core.env.bootstrap_cli_env`.
- Must not import: `app.services.ir_discovery.agent`,
  `app.services.ir_discovery.exchange.{bse_client, nse_client, discover}`,
  any FastAPI or HTTP-router code.

## Verification checklist

- [ ] Re-running on a fully-resolved DB prints "Nothing to do" and
      exits 0.
- [ ] `--dry-run` prints the same proposed actions twice in a row
      (idempotent preview).
- [ ] `--auto-accept` never prompts on stdin.
- [ ] Fuzzy matches below `--fuzzy-cutoff` are skipped, not silently
      written.
- [ ] After a successful run, `discover_period_assets` for the
      affected companies hits BSE first.
