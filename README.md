# CapitalNerve

An Indian-markets intelligence layer built around the investor workflow:

> **Company → Event → Signal → Card → Evidence → Watch Item**

Rather than a document repository, CapitalNerve surfaces only the cards that matter, explains them, and proves every claim with extracted evidence the user can verify.

This repo contains:

- `backend/` — FastAPI + SQLAlchemy 2.0 + Postgres, JWT auth, full schema for events / extracted values / facts / metrics / signals / cards / evidence, ingestion pipeline, and admin review queue.
- `frontend/` — Vite + React + TypeScript + TailwindCSS dark theme, structured around the four MVP surfaces (Intelligence Feed, Company Page, Event Detail, Signal Screener) plus Watchlist, Search, Evidence Viewer, and Admin Review.

The system is production-only: there is no seeded demo company, event, or card. Every piece of intelligence visible in the UI comes from a real document that an admin uploaded through `POST /ingest/upload`, parsed and analysed by the pipeline.

---

## Quickstart (Docker)

```bash
docker compose up --build
```

That brings up:

- `db` — Postgres 16 on `:5432`
- `backend` — FastAPI on `:8000` (runs Alembic migration + catalog seed on first boot)
- `frontend` — Vite dev server on `:5173`

Open <http://localhost:5173>, sign up, and start ingesting filings.

### Bootstrapping an admin

The catalog seeder will create a single admin on first boot if you set the following environment variables on the `backend` container (`docker-compose.yml` or your deploy):

```bash
ADMIN_EMAIL=you@example.com
ADMIN_PASSWORD=a-strong-password
ADMIN_FULL_NAME="Your Name"   # optional
```

Without those vars no users are created automatically; use `POST /auth/signup` or create them through your usual provisioning flow.

---

## Local development (no Docker)

Postgres is the only external dep. Start it via Docker if you don't have it:

```bash
docker run -d --name capitalnerve-db -p 5432:5432 \
  -e POSTGRES_USER=capitalnerve \
  -e POSTGRES_PASSWORD=capitalnerve \
  -e POSTGRES_DB=capitalnerve \
  postgres:16-alpine
```

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit DATABASE_URL, JWT_SECRET, LLM_PROVIDER, ADMIN_*
alembic upgrade head
python -m app.seed.seed_catalog
uvicorn app.main:app --reload
```

The API runs at <http://localhost:8000>. OpenAPI docs at <http://localhost:8000/docs>.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api/*` to `http://localhost:8000` (configurable via `VITE_API_BASE`).

---

## Onboarding a real issuer

1. Sign in with an admin account.
2. Go to `/admin/ingest`.
3. Create the issuer (legal name, NSE symbol, sector). The form calls `POST /admin/companies`.
4. Pick the new issuer, choose event type / document type, set the period label (for example `Q4 FY2025-26`), upload the PDF.
5. The worker drains `extraction_jobs`, runs the pipeline (parse → extract → normalize → metrics → signals → cards), and publishes cards whose confidence is at or above `AUTO_PUBLISH_CONFIDENCE`.
6. Lower-confidence cards land in the Review Queue at `/admin/review`; approve via `PATCH /review/{id}`.

---

## What the MVP includes

### Surfaces

1. **Home / Intelligence Feed** — Market summary strip + tabbed card feed (All / Watchlist / Results / Red Flags / Positive / Management) + right-side watchlist & alerts panel.
2. **Company Page** — Header with badges, latest summary, top intelligence cards, financial snapshot table + 8-quarter trend sparklines, event timeline, source documents.
3. **Event Detail Page** — Verdict + signal badges, analyst concern heatmap (for concalls), management commentary facts, vertical card stack ordered by investor reading flow.
4. **Signal Screener** — Filter chips + filters + table view; tap any row to open the company.
5. **Watchlist** — Per-company change summary + "watch items" (thesis monitors).
6. **Search** — Returns Companies + Cards + Events (not just documents).
7. **Document / Evidence Viewer** — Split view with markdown rendering of source pages and right-side evidence panel showing extracted values, source quotes, calculations, and confidence.
8. **Admin Review Queue** — Pending extractions and low-confidence items (admin only).
9. **Admin Ingest** — File picker, company/event/period selectors, live "Recent jobs" table.

### Card system

Every card has:

- Type & headline & one-line summary
- Signal direction badge (Positive / Negative / Mixed / Neutral)
- Severity badge (Low / Medium / High / Critical)
- Confidence badge (numeric + level)
- 3 key metrics
- Investor question
- Watch-next CTA
- Linked evidence — each evidence row carries source text, page reference, and calculation

### Data model

The schema follows the spec exactly:

```
extracted_values     -- what the model read
financial_statement_facts -- what was normalized
calculated_metrics   -- what was calculated
generated_signals    -- what was interpreted
intelligence_cards   -- what the user sees
card_evidence        -- why the user can trust it
```

Plus master data (companies, sectors, periods), event/document tables, segment & concall & presentation & announcement facts, and user/watchlist/alert tables.

### Ingestion pipeline

`POST /ingest/upload` (multipart) accepts a PDF / markdown / text file, stores it under `STORAGE_DIR` (sha256-keyed dedupe), and creates an `extraction_jobs` row in `PENDING`.

The worker (`backend/app/workers/pipeline_worker.py`) drains the queue and walks every stage in [`backend/app/services/pipeline/`](backend/app/services/pipeline/_BASE.md):

```
storage bytes → parse → extract (LLM) → normalize → metrics → signals → cards
```

By default it runs **inside** the FastAPI process (`WORKER_INPROCESS=true`). For production, set `WORKER_INPROCESS=false` and run the standalone CLI:

```bash
python -m app.workers.run
```

LLM provider is pluggable: set `LLM_PROVIDER=anthropic` (or `openai`) and the matching API key for real structured extraction. `LLM_PROVIDER=mock` is a deterministic regex fallback for local development; it is rejected when `APP_ENV=production`.

Confidence ≥ `AUTO_PUBLISH_CONFIDENCE` (default 80) auto-publishes the resulting cards; below that they stay unpublished and the Review Queue stays OPEN until an admin approves via `/admin/review`.

Admins can drive the whole flow from `/admin/ingest` — file picker, company / event / period selectors, plus a live "Recent jobs" table that polls `/ingest/jobs` every 4 seconds.

---

## Repository layout

```
.
├── backend/
│   ├── app/
│   │   ├── core/        # config, security, deps
│   │   ├── db/          # base, session, enums
│   │   ├── models/      # SQLAlchemy 2.0 models grouped by domain
│   │   ├── schemas/     # Pydantic v2 request/response models (common + v1)
│   │   ├── routers/     # auth, watchlist, search, documents, ingest, review, admin, v1/*
│   │   ├── services/    # read-side enrichment + pipeline package
│   │   ├── seed/        # catalog bootstrap (line items, metrics, signals, periods)
│   │   ├── workers/     # pipeline worker loop
│   │   └── main.py
│   ├── alembic/         # versions/0001_initial.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── start.sh
├── frontend/
│   ├── src/
│   │   ├── api/         # client, types
│   │   ├── components/  # cards, evidence, layout, common
│   │   ├── pages/       # routes
│   │   ├── store/       # zustand auth
│   │   ├── lib/         # formatters
│   │   └── styles.css
│   ├── tailwind.config.ts
│   └── vite.config.ts
├── docker-compose.yml
└── README.md
```

---

## Design notes

- The card priority used for feed ranking is per spec §19 — financial materiality + severity + surprise + confidence + relevance.
- Card colours follow spec §11 — positive/negative/mixed/neutral/low-confidence — and always include a label, never colour alone.
- Mobile uses a feed-first layout with sticky bottom nav and bottom-sheet card drawers; desktop uses the 3-column layout (sidebar + main + context panel).
- The frontend talks to a single versioned API surface under `/v1`; the legacy flat routes were removed.

---

## Agent standards

Every meaningful source file in this repo ships with a colocated `*.COMPONENT.md` standards doc, plus a folder-level `_BASE.md`. Together they describe the conventions that keep the codebase symmetric.

Start at [AGENTS.md](AGENTS.md) for the agent workflow and the inventory of `_BASE.md` files. Before editing any file, read its colocated `*.COMPONENT.md` and the matching folder baseline.
