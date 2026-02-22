# Groceries Optimizer

Lightweight grocery optimizer: fetches products from stores, scores them and builds an optimized cart.

Quick links
- API: `/optimize`, `/health` (FastAPI)
- Frontend: Streamlit `app.py`

Quick start (local, Docker Compose)

1. Build & run containers:

```bash
cd groceries
docker compose up --build
```

2. Open UI: http://localhost:8505 (or host port mapped in `docker-compose.yml`)
3. API docs: http://localhost:8000/docs

Local dev (without Docker)

1. Create venv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the API:
```bash
uvicorn api.service:app --reload --host 0.0.0.0 --port 8000
```

3. Run the frontend (Streamlit):
```bash
streamlit run app.py
```

Database migration and data
- The project defaults to SQLite locally (`groceries.db`) and Postgres via `DATABASE_URL`.
- On container startup the API waits for Postgres and will automatically load `catalog/normalized_catalog.json` and migrate an existing `groceries.db` into Postgres.

Manual migration (inside API container):

```bash
docker compose exec api python /app/scripts/migrate_sqlite_to_postgres.py
```

CI/CD (GitHub Actions)
- Workflow: `.github/workflows/ci-cd.yml` builds images and pushes to GHCR, then optionally triggers a Render deploy.
- To enable Render deploys, add these repository secrets in GitHub:
  - `RENDER_API_KEY` — your Render API key
  - `RENDER_SERVICE_ID` — Render service id (without `srv-` prefix)

Render deployment
1. Create two services on Render: one for the API and one for the frontend (or use a single service and route).
2. Configure the service to use the GHCR image or let GitHub Actions trigger a deploy via the Render API.

Testing the API

```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/optimize \
  -H "Content-Type: application/json" \
  -d '{"items":["piim","banaan"],"stores":["rimi"]}' | jq
```

Notes
- Keep secrets out of the repo. Use GitHub Secrets for `RENDER_API_KEY`/`RENDER_SERVICE_ID`.
- For production use a managed Postgres (Render Postgres) and configure backups.

If you want, I can add a `render.yaml` manifest or a short `terraform` snippet to provision Render services.

Render manifest
----------------
I added a `render.yaml` manifest you can use to create two services on Render (API and frontend). To deploy using the manifest:

1. Connect your GitHub repo to Render and enable deploys from the `main` branch.
2. In the Render dashboard import `render.yaml` (Account → Services → New → Import from repo). Render will create the services and build from your repo.
3. Set the following environment variables in Render (Settings → Environment):
  - `DATABASE_URL` — your Postgres connection string
  - `RENDER_API_KEY` and `RENDER_SERVICE_ID` are used by the GitHub Actions workflow (if configured)

The manifest is a starting point — you may want to update the `GROCERIES_API_URL` env var to the actual API public URL once Render creates the API service.
