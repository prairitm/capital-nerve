# CapitalNerve v4

## Start the app

From the repo root:

```bash
./v4/start_all.sh
```

This starts the frontend, backend API, and all seven microservices:

- Frontend: `http://localhost:5174`
- Backend API: `http://127.0.0.1:8010`
- Microservices: `http://127.0.0.1:8020-8026`
- Logs: `v4/logs/`

Use reload mode for local FastAPI development:

```bash
RELOAD=1 ./v4/start_all.sh
```

Stop everything with `Ctrl-C`.

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
