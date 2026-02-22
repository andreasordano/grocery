docker compose up --build
# Groceries Optimizer

Lightweight grocery optimizer: calls store APIs live, scores products, and builds the cheapest cart. No local product DB required.

Quick links
- API: `/optimize`, `/health` (FastAPI)
- Frontend: Streamlit `app.py`

Quick start (local, Docker Compose)

1) Build & run containers (API + Streamlit; no DB needed)

```bash
cd groceries
docker compose up --build
```

2) Open UI: http://localhost:8505 (or the mapped port in `docker-compose.yml`)
3) API docs: http://localhost:8000/docs

Local dev (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run API
uvicorn api.service:app --reload --host 0.0.0.0 --port 8000

# Run frontend
streamlit run app.py
```

Environment
- `GROCERIES_API_URL` (frontend) — URL of the FastAPI service (defaults to http://localhost:8000)
- `FETCH_CACHE_TTL`, `FETCH_CACHE_MAX`, `PER_STORE_LIMIT` — optional knobs for fetch caching/limits

Testing the API

```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/optimize \
  -H "Content-Type: application/json" \
  -d '{"items":["piim","banaan"],"stores":["rimi","selver","barbora"]}' | jq
```

Notes
- Product catalog files and DB seeding scripts were removed; the app searches stores live using the user’s typed terms.
- Keep secrets out of the repo; set env vars in your deployment platform.
