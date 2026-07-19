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

## Backfill the administrator watchlist

With the seven pipeline services running, process Financial Results for every
company on the active administrator's watchlist over the latest eight completed
calendar quarters (oldest first):

```bash
.venv/bin/python v4/run_admin_watchlist_history.py
```

Preview the generated `run.py` commands without calling the services:

```bash
.venv/bin/python v4/run_admin_watchlist_history.py --dry-run
```

If the database has multiple active administrators, select one with
`--admin-email`. Use `--as-of YYYY-MM-DD` for a reproducible cutoff and append
extra `run.py` options after `--`, for example `-- --verbose`.

## Remove all company data

Stop the v4 services, review the dry-run report, then explicitly confirm the
cleanup:

```bash
.venv/bin/python v4/remove_all_company_data.py
.venv/bin/python v4/remove_all_company_data.py --confirm
```

This removes all companies, their pipeline data, monitor jobs, watchlist
entries, stored PDFs, and parsed-document cache. It preserves user accounts,
user settings, and the static fact-definition catalog.

## Deploy publicly on a Raspberry Pi

On a 64-bit Raspberry Pi OS installation, clone this repository and run:

```bash
chmod +x v4/deploy_pi.sh
./v4/deploy_pi.sh
```

The installer prompts for the initial administrator credentials and OpenAI API
key. It then installs the OS, Python, Node.js, Caddy, and Tailscale dependencies;
builds the frontend; creates boot-persistent systemd services; and publishes the
application over HTTPS using a free, stable Tailscale Funnel `*.ts.net` address.
No purchased domain, public IP address, or router port forwarding is required.

Run the installer as the normal Pi user, not as root. It uses `sudo` for system
configuration. The services and Caddy bind only to `127.0.0.1`; only the Funnel
URL is public. The administrator bootstrap password is removed from the service
environment after the account is created.

## Authentication and roles

The v4 API uses a separate writable application database for users, sessions,
and watchlists. The analytics database remains read-only to the web API and
continues to be owned by the extraction pipeline.

- `MEMBER` users can access every backend-added company and maintain their own
  watchlist.
- `ADMIN` users have the same research access and can create, update,
  deactivate, reactivate, and reset other user accounts from **Users**. They
  can also adjudicate uncertain extracted facts from **Reviews**.
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
| `V4_COMPANY_SERVICE_URL` | `http://127.0.0.1:8020` | Step 1 service used to register a newly monitored NSE company |
| `V4_NSE_EQUITY_CSV_URL` | official NSE equity CSV | Source for the searchable NSE company directory |
| `V4_NSE_REFRESH_HOURS` | `24` | Maximum age of the cached NSE directory |
| `V4_NSE_REQUEST_TIMEOUT_SECONDS` | `30` | Timeout for directory downloads and company registration |
| `V4_NSE_REFRESH_ON_STARTUP` | `true` | Refresh the directory at backend startup when it is stale |
| `V4_PUBLIC_APP_URL` | `https://capital-nerve.taildeaa7c.ts.net` | Public origin used in notification links |
| `V4_SMTP_HOST` | `smtp.gmail.com` | SMTP server for watchlist email |
| `V4_SMTP_PORT` | `587` | STARTTLS SMTP port |
| `V4_SMTP_USERNAME` | `capitalnerve@gmail.com` | Gmail SMTP account |
| `V4_SMTP_PASSWORD` | unset | Gmail App Password; email delivery stays disabled without it |
| `V4_EMAIL_FROM_ADDRESS` | `capitalnerve@gmail.com` | Email From address |
| `V4_EMAIL_FROM_NAME` | `CapitalNerve` | Email From display name |

Production deployments must set `V4_COOKIE_SECURE=true`, serve the frontend and
API over HTTPS, and restrict `V4_CORS_ORIGINS` to the deployed frontend origin.

## Watchlist email notifications

Users can opt in from **Profile** and choose which supported filing types should
generate email. A filing is queued for email only after the full pipeline has
completed, and delivery is retried independently from extraction. Custom
notification addresses must be verified; the account login email is trusted by
default. Removing a company or disabling alerts cancels unsent watchlist mail.

Delivery uses Gmail SMTP with STARTTLS. Enable two-step verification on
`capitalnerve@gmail.com`, create a Gmail App Password, and expose it only as
`V4_SMTP_PASSWORD`. The Raspberry Pi installer prompts for this secret without
echoing it and writes it to the protected service environment. Use **Send test
email** on Profile after deployment to verify delivery.

## NSE company search

The **Companies** search checks both the processed CapitalNerve coverage universe
and a locally cached copy of NSE's official equity-segment security list. Search
results that are not covered appear under **More companies on NSE** and can be
added with **Start monitoring**.

The directory is stored in the writable application database and refreshed at
backend startup when it is older than `V4_NSE_REFRESH_HOURS`. A failed download
does not delete the last successful snapshot. The analytics database remains
read-only to the backend: when a user starts monitoring a new symbol, the
backend asks the Step 1 company service to register it before adding it to the
user's watchlist.

Monitoring begins at the time the company is added. Previously published
filings are not automatically processed; future supported filings are handled
by the filing monitor.

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

## Fact review queue

Extraction outcomes marked `review_required` appear in the administrator-only
**Reviews** page. Each item shows all matching observations, values, confidence,
PDF page evidence, reporting basis, and period. Approval requires selecting an
observation; rejection requires a reviewer note; either decision can be
reopened until an approval has been applied.

Review decisions are written to the application database with the administrator
and timestamp. They do not mutate the read-only analytics database and do not
auto-publish a fact. A later controlled reconciliation step must apply approved
decisions to analytics before metrics or signals may consume them. Facts whose
resolution status is not exactly `resolved` are excluded from those downstream
calculations.

Preview all pending approvals without writing either database:

```bash
python v4/microservices/reconcile_reviews.py
```

After checking the JSON preview, apply validated approvals and recompute
dependent metrics and signals once for each affected event:

```bash
python v4/microservices/reconcile_reviews.py \
  --apply \
  --applied-by "operator@example.com"
```

Use `--resolved-fact-id ID` one or more times to limit a run. Application is
idempotent and resumable: analytics stores an immutable before/after ledger,
while the app database records application and recomputation status. The
reconciler refuses stale decisions, mismatched period/basis/dimensions, missing
values, and observations without page-level source evidence. `--no-recompute`
is available only for maintenance recovery and leaves downstream work pending.

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
