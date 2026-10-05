# Groceries

"Go here. Buy this." — tell the app what you need and it recommends **one store** with a ready basket, plus alternatives.
Product prices are fetched live from store e-shops (Selver, Barbora, Rimi); there is no local product database.

Two missions:
- **🍽️ Dinner tonight** — pick one of 10 dinners and the number of people → one store (Selver or Rimi) with a priced basket.
- **🛒 Shopping list** — type generic items (free-text search across Selver, Barbora, Rimi; best guess).

- **Frontend:** one self-contained page (`web/index.html`, plain HTML/CSS/JS), served by the API at `/`
- **API:** FastAPI (`api/service.py`) — `GET /recipes`, `POST /dinner`, `POST /optimize`, `POST /events`, `GET /health`
- **Events DB:** Postgres (via `DATABASE_URL`), falling back to SQLite at `logs/events.db`

See `diagram.md` for the architecture.

## Run locally with Docker (recommended)

Requires Docker Desktop running.

```bash
docker compose up --build        # add -d to run in the background
```

| Service | URL |
|---|---|
| App | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Postgres | `localhost:5433`, user/password/db: `groceries` |

The source folder is mounted into the containers, so code changes are picked up on restart:
Python changes need `docker compose restart api`; changes to `web/index.html` or `data/*.yaml` only need a browser refresh.

Stop with `docker compose down`. Event data lives in the `pgdata` volume and survives restarts;
`docker compose down -v` **deletes it**.

## Run locally without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# API + web app (events go to logs/events.db unless DATABASE_URL is set)
uvicorn api.service:app --reload --port 8000
```

Open http://localhost:8000.

## Testing with users

Give each tester a personal link so repeat usage can be measured per person:

```
http://localhost:8000/?u=maria
```

Every recommendation is logged (`dinner` or `optimize` event), the 👍/👎 buttons log `accept`/`reject`,
and "A product looks wrong?" logs `wrong_product` — use those to decide which rule to fix.
Without `?u=` the user is anonymous (only a per-visit session id is stored).

### Looking at the data

```bash
docker compose exec db psql -U groceries
```

```sql
-- Latest events
SELECT ts, user_id, type, data->>'recommended_store' AS store, data->>'latency_s' AS latency
FROM events ORDER BY ts DESC LIMIT 20;

-- Per tester: requests, accepts, rejects, active days
SELECT user_id,
       count(*) FILTER (WHERE type IN ('dinner', 'optimize')) AS requests,
       count(*) FILTER (WHERE type = 'accept')   AS accepts,
       count(*) FILTER (WHERE type = 'reject')   AS rejects,
       count(DISTINCT ts::date)                  AS active_days
FROM events GROUP BY user_id ORDER BY requests DESC;
```

## Recipes and ingredient rules

- `data/recipes.yaml` — dinners, ingredient amounts for 2 people, pantry items (not priced).
- `data/rules.yaml` — per ingredient and store: search query + store category + required/excluded words.
  The cheapest acceptable product for the amount needed wins (whole packs; loose goods by weight).
  No product IDs are pinned, so product churn needs no upkeep.

Write or check a rule against live data:

```bash
python -m scripts.rules_preview                     # what every rule picks, per store
python -m scripts.rules_preview kanafilee --all     # also rejected products and why
python -m scripts.rules_preview --raw "hapukapsas" --store selver   # raw search with categories
```

Adding a recipe: add it to `recipes.yaml`; only new ingredients need rules. `tests/test_catalog.py`
fails if a recipe uses an ingredient without rules for both stores.

### Daily health check

`.github/workflows/healthcheck.yml` runs `python -m scripts.healthcheck` every day at 05:00 UTC. If a store
integration breaks, a rule stops finding products, or a recipe total looks wrong, it opens (or comments on)
a GitHub issue labelled `healthcheck` — that is the only maintenance signal to watch. Run it locally the same way.
Note: GitHub disables scheduled workflows after 60 days without repository activity.

## API examples

```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/dinner \
  -H "Content-Type: application/json" \
  -d '{"recipe_id":"kana_riisikauss","servings":2,"user_id":"maria"}' | jq '.baskets[] | {store, total_price, missing}'

curl -s -X POST http://localhost:8000/optimize \
  -H "Content-Type: application/json" \
  -d '{"items":["piim","banaan"],"stores":["rimi","selver","barbora"],"user_id":"maria"}' | jq '.info'
```

## Tests

```bash
pip install pytest
python -m pytest -q tests
```

Tests don't call the stores. To check the store integrations and rules against the live sites:
`python -m scripts.healthcheck`.

## Configuration

| Variable | Used by | Default |
|---|---|---|
| `DATABASE_URL` | API | unset → SQLite |
| `EVENTS_DB` | API (SQLite path) | `logs/events.db` |
| `FETCH_CACHE_TTL` / `FETCH_CACHE_MAX` | API | `21600` s / `512` |
| `PER_STORE_LIMIT` | API | `6` candidates per item per store |
| `FETCH_WORKERS` | API | `12` parallel store requests |

Keep secrets out of the repo; set env vars in your deployment platform.
