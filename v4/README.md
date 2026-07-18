# CapitalNerve v4

## Start the app

From the repo root:

```bash
.venv/bin/pip install -r v4/backend/requirements.txt
cd v4/frontend && npm install && cd ../..
```

Then start v4 and bootstrap the first administrator:

```bash
V4_ADMIN_EMAIL=admin@example.com \
V4_ADMIN_PASSWORD='replace-with-a-strong-password' \
./v4/start_all.sh
```

On the first start, those variables create the initial administrator. The
bootstrap is idempotent: later starts never overwrite that account or reset its
password. Both variables can be removed after the administrator exists.

This starts the frontend, backend API, the seven-step pipeline, and the filing monitor:

- Frontend: `http://localhost:5174`
- Backend API: `http://127.0.0.1:8010`
- Microservices: `http://127.0.0.1:8020-8027`
- Logs: `v4/logs/`

Use reload mode for local FastAPI development:

```bash
RELOAD=1 ./v4/start_all.sh
```

Stop everything with `Ctrl-C`.

## Authentication and roles

The v4 API uses a separate writable application database for users, sessions,
and watchlists. The analytics database remains read-only to the web API and
continues to be owned by the extraction pipeline.

- `MEMBER` users can access every backend-added company and maintain their own
  watchlist.
- `ADMIN` users have the same research access and can create, update,
  deactivate, reactivate, and reset other user accounts from **Users**.
- New users receive a generated temporary password and must replace it on first
  login. There is no public signup or email recovery flow.
- Sessions are stored server-side, expire after seven days, and use an
  HttpOnly cookie. Deactivation and password resets revoke existing sessions.

Application schema migrations run automatically at backend startup. The
default database is `v4/data/capital_nerve_app.db` and is ignored by git.

| Variable | Default | Purpose |
| --- | --- | --- |
| `V4_APP_DB_PATH` | `v4/data/capital_nerve_app.db` | User/session/watchlist database |
| `V4_ADMIN_EMAIL` | unset | Initial administrator email |
| `V4_ADMIN_PASSWORD` | unset | Initial administrator password (minimum 12 characters) |
| `V4_SESSION_TTL_HOURS` | `168` | Absolute session lifetime |
| `V4_COOKIE_SECURE` | `false` | Enable for HTTPS deployments |
| `V4_CORS_ORIGINS` | local frontend origins | Credentialed frontend origins |

Production deployments must set `V4_COOKIE_SECURE=true`, serve the frontend and
API over HTTPS, and restrict `V4_CORS_ORIGINS` to the deployed frontend origin.

## Watchlist filing monitor

The service on port `8027` checks each distinct watched NSE company every two
minutes. New financial results, investor presentations, and earnings-call
transcripts are processed once and appear in the feeds of all users currently
watching that company. Existing processed history is visible immediately when a
company is added; historical filings are not reprocessed.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONITOR_POLL_INTERVAL_SECONDS` | `120` | Seconds between successful company polls |
| `MONITOR_MAX_ATTEMPTS` | `5` | Maximum full-pipeline attempts per filing |
| `MONITOR_PIPELINE_VERSION` | `v4-1` | Idempotency version for durable jobs |
| `MONITOR_FLOW_TIMEOUT_SECONDS` | `1800` | Timeout for one exact-document flow |

## Run the 7-step microservice flow

Start services first, then run the flow from another terminal:

```bash
.venv/bin/python v4/microservices/run.py \
  --symbol ITC \
  --from-date 01-04-2026 \
  --to-date 30-06-2026 \
  --event-type "Financial Results" \
  --source-mode nse_auto
```

To run all supported event types in sequence:

```bash
.venv/bin/python v4/microservices/run.py \
  --symbol ITC \
  --from-date 01-04-2026 \
  --to-date 30-06-2026 \
  --all-event-types \
  --source-mode nse_auto
```

If one event type has no matching document announcement, the runner marks that
event type as `skipped`, continues with the remaining event types, and prints a
final run report.

Supported event types:

- `Financial Results`
- `Investor Presentation`
- `Earnings Call Transcript`

Supported source modes:

- `nse_auto`
- `ir_agent`
- `manual_url`
- `local_file`

For source modes that require extra fields, pass a document request:

```bash
.venv/bin/python v4/microservices/run.py \
  --symbol ITC \
  --from-date 01-04-2026 \
  --to-date 30-06-2026 \
  --event-type "Financial Results" \
  --document "document_type=financial_result,source_mode=manual_url,source_url=https://example.com/file.pdf"
```

For local files:

```bash
.venv/bin/python v4/microservices/run.py \
  --symbol ITC \
  --from-date 01-04-2026 \
  --to-date 30-06-2026 \
  --event-type "Financial Results" \
  --document "document_type=financial_result,source_mode=local_file,local_path=/absolute/path/to/file.pdf"
```

Useful options:

```bash
# Log full step responses
.venv/bin/python v4/microservices/run.py ... --verbose

# Call values synchronously instead of the background job endpoint
.venv/bin/python v4/microservices/run.py ... --values-sync

# Tune Step 4 worker counts
.venv/bin/python v4/microservices/run.py ... \
  --values-parse-workers 2 \
  --values-extraction-workers 2
```

`run.py` expects the microservices to be running on ports `8020-8026`. The frontend and backend API are useful for browsing results, but they are not required by the flow runner.

## Catalogs

The canonical v4 catalogs live in `v4/microservices/catalog/`. Financial
results, investor presentations, and earnings calls are evaluated with
independent fact, metric, and signal catalogs declared in `manifest.json`.
Presentation and call catalogs can opt into a small named set of financial
metrics for cross-document comparisons; they do not inherit the full results
catalog.

`display.json` is the minimal product-facing catalog. It defines headline facts,
ranked metrics, evidence groups, signal allow-lists, de-duplication groups, and
the maximum of three primary signals per document. The extraction catalogs stay
broader so supporting evidence remains available in the drill-down.

Every v4 service uses that directory by default. The existing `*_CATALOG_DIR`
environment variables can still point all services at another catalog tree with
the same manifest layout.

## Verification

From the repository root:

```bash
.venv/bin/pip install -r v4/backend/requirements.txt
.venv/bin/python -m unittest discover -s v4/backend -p 'test_*.py' -v
cd v4/frontend
npm install
npm test
npm run build
```
