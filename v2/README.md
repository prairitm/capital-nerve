# Capital Nerve v2

FastAPI serving layer over the SQLite store (`data/capital_nerve.db`). The UI lives in the separate [capital-nerve](https://github.com/prairitm/capital-nerve) repo under `v1/frontend` — a Vite + React app that talks to this API through a dev proxy.

## Quick start

You need two terminals: one for the API, one for the frontend.

### 1. Backend (required for the UI)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Frontend

```bash
cd v1/frontend
npm install
npm run dev
```

Open the app at [http://localhost:5173](http://localhost:5173).

The Vite dev server proxies `/api/*` to `http://localhost:8000`, so the frontend does not need a separate API URL in local dev.

## Frontend commands

| Command | Description |
|---------|-------------|
| `npm install` | Install dependencies (first time, or after `package.json` changes) |
| `npm run dev` | Start the dev server on port **5173** with hot reload |
| `npm run build` | Production build (`dist/`) |
| `npm run preview` | Serve the production build locally |

### Optional: point the proxy at a different API

```bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

Default is `http://localhost:8000` (see `v1/frontend/vite.config.ts`).

## Login

With the default `.env` from `.env.example`, a dev admin user is created on API startup:

- **Email:** `dev@capitalnerve.local`
- **Password:** `dev`

You can also sign up at `/signup` — users are stored in memory for the session.

## Troubleshooting

- **Blank page or API errors** — confirm the backend is running on port 8000 before starting the frontend.
- **CORS errors** — ensure `CORS_ORIGINS` in `.env` includes `http://localhost:5173` (the default).
- **Port in use** — Vite uses 5173; the API uses 8000. Change ports in `vite.config.ts` or the `uvicorn` command if needed.
