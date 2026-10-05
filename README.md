# Groceries

"Go here. Buy this." — tell the app what you need and it recommends **one store** with a ready basket, plus alternatives.
Product prices are fetched live from store e-shops (Selver, Barbora, Rimi); there is no local product database.

Two missions:
- **🍽️ Dinner tonight** — pick one of 10 dinners, the number of people and anything else you need on the way
  → one store (Selver, Rimi or Barbora) with a priced basket.
- **🛒 Shopping list** — type items. Words that match a known ingredient (piim, munad, pasta, …) use its rule;
  anything else is a free-text best guess. Searches Selver, Rimi and Barbora (Barbora stands in for Maxima).

- **Frontend:** one self-contained page (`web/index.html`, plain HTML/CSS/JS), served by the API at `/`
- **API:** FastAPI (`api/service.py`) — `POST /basket` (used by the web app), `GET /recipes`, `POST /events`, `GET /health`;
  older `POST /dinner` and `POST /optimize` still work
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

Every recommendation is logged as a `basket` event (with the user's preferences). The receipt logs `accept`/`reject`
(with the store chosen, which may not be the cheapest), `view_store` (comparing stores), `preference`
(choosing another product or typing preference words) and `wrong_product` — use those to decide which rule to fix.
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
       count(*) FILTER (WHERE type IN ('basket', 'dinner', 'optimize')) AS requests,
       count(*) FILTER (WHERE type = 'accept')   AS accepts,
       count(*) FILTER (WHERE type = 'reject')   AS rejects,
       count(DISTINCT ts::date)                  AS active_days
FROM events GROUP BY user_id ORDER BY requests DESC;
```

## Recipes and ingredient rules

- `data/recipes.yaml` — dinners, ingredient amounts for 2 people, pantry items (not priced), and per ingredient
  the `aliases` people type in the shopping list (e.g. munad: munad, muna, kanamunad).
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

### Preferences

On the receipt, tap an item to see every acceptable product for it at that store, cheapest first, and pick one.
The sheet then suggests words from the picked product's name (brand, type, fat %), e.g. *spagetid*, *laktoosivaba*,
*tere*. Tapping one applies it to the other stores and shows straight away what it would pick there, or that
nothing matches and the cheapest stays. Matching tolerates spelling: "spaghetti" matches "Spagetid".

Each receipt says when preferences are in use ("Using your preferences for Makaronid") and links to
**Edit preferences**, which lists them with Remove / Remove all. They're kept in the browser (`localStorage`)
and sent with each request:

```json
{"makaronid": {"label": "Makaronid", "words": ["spagetid"], "products": {"barbora": "Spagetid Nr 7 PRESTO 400g"}}}
```

## API examples

```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/basket \
  -H "Content-Type: application/json" \
  -d '{"recipe_id":"pasta_hakklihaga","servings":2,"items":["piim"],"prefs":{"piim":{"words":["laktoosivaba"]}},"user_id":"maria"}' \
  | jq '.baskets[] | {store, total_price, missing}'

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
