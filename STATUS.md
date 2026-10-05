# Project status and next steps

_Last updated: 6 October 2026. Written to pick the project up again later._

**Thesis:** "Don't compare groceries. Decide what to do." Someone leaving work picks a dinner and gets
**one store and a shopping list** ("Go to Barbora: 5,92 €"), not a price spreadsheet.

**The question that matters:** will normal people use this to make grocery decisions **repeatedly**?
Not "can it compare prices"; that already works, and [toiduhind.ee](https://toiduhind.ee) does it for free.

---

## Where we are against the original plan

The plan was **30% engineering / 70% validation** over 2–4 weeks. So far it has been close to 100%
engineering: the app is far ahead of what validation needed, and **no real users have tried it yet**.
All 61 events in the local database are from one person (the founder).

| Week | Planned | Status |
|---|---|---|
| 1 | Fix Rimi, parallel fetching, single-store basket, event logging | ✅ Done, plus much more (see below) |
| 1 | ~10 interviews about past behaviour ("walk me through your last 3 grocery trips") | ❌ Not started |
| 1 | Recruit 20–30 concierge testers (not friends) | ❌ Not started |
| 1 | Decide kill criteria before testing | ❌ Not done (draft below) |
| 2 | Concierge test by hand over chat: "dinner tonight" vs "this week's offers → dinners" | ❌ Not started |
| 3 | Build the card UI only for the framing people came back for | ⚠️ Built anyway, for "dinner tonight" |
| 4 | Push to ~100 users, compare against kill criteria | ❌ Not started |
| — | One afternoon checking shelf prices in a physical Selver and Rimi vs the e-shop (~25 items) | ❌ Not done |

### Built beyond the plan
- Receipt-style web app (`web/index.html`): Dinner and Shopping list modes, compare stores, tap an item to
  pick another product, preferences grounded in real product names, "Edit preferences".
- Hand-written ingredient rules for **Selver, Rimi and Barbora** (`data/rules.yaml`, 26 ingredients), with
  fallbacks (sauerkraut → praekapsas) and typed-word aliases (`data/recipes.yaml`).
- 10 dinners with amounts for 2, scaled by people; extra items on a dinner trip.
- Daily health check (`scripts/healthcheck.py`, GitHub Actions) that opens an issue when a store or rule breaks.
- Postgres in Docker Compose, event log, 61 tests, README.

---

## Missing, in priority order

### 1. Validation (the actual next step)
- [ ] **Write the kill criteria now**, before anyone tests. Draft:
      - 20–30 testers who are not friends, 2 weeks.
      - **Continue** if ≥ 30% make a second request **without being prompted** within 7 days, and ≥ 40% of
        recommendations get "I'll go there".
      - **Stop or rethink** if < 25% come back unprompted.
- [ ] **10 interviews** about past behaviour, not the idea. Expect "I go to the closest store"; that answer matters.
- [ ] **Recruit testers**: Estonian Facebook groups, r/Eesti, office chats. Give each a personal link `/?u=name`.
- [ ] **Put the app online** so testers can reach it (see Deployment). Or run the concierge version by hand
      over chat first and use the app as a back-office tool.
- [ ] **Test the second framing**, "this week's offers → 3 dinners": weekly, habit-forming, and something
      ChatGPT can't answer. It needs campaign data (flyers / offer pages), which we don't collect yet.
- [ ] **Shelf-price check**: ~25 ingredients, physical store vs e-shop. If the gap is under 5–10% outside
      campaigns, e-shop prices are good enough.

### 2. Deployment (blocks real users)
- [ ] **Deploy somewhere.** `render.yaml` defines only the API service (it now also serves the web app);
      the old frontend service was removed.
- [ ] **Add a Postgres database** and set `DATABASE_URL` on the API. Without it, events go to SQLite on
      Render's disk and are **lost on every deploy**.
- [ ] **Run the health-check workflow once on GitHub** ("Run workflow"). It has never run there, and store
      sites might block GitHub's servers.
- [ ] Note: GitHub turns scheduled workflows off after 60 days without repository activity.

### 3. Product direction agreed on 6 Oct 2026 (in progress)
- [x] **Show discounts** on the receipt (regular price, % off, offer end date, card price, multi-buy notes, "You save").
- [x] **Pantry items can be added** to a dinner trip (tap "õli" under "Have at home").
- [ ] **One list with Ideas:** merge Dinner and Shopping list. Free items are the core; recipes become ideas
      that add their ingredients to the list as editable items. No new hand-written recipes.
- [ ] **"Save as my dinner":** users keep their own lists (zero upkeep, shows what people cook).
- [ ] **Featured ideas from discounts**, computed automatically ("Shakshuka is 30% cheaper at Rimi this week").
      Later the slot for store-paid placement, always labelled.

### 4. Product gaps found while testing
- [ ] **Quantities in the shopping list** ("2 piim", "kartul 2 kg"). Today an item means one pack, or 800 g
      for loose goods (borrowed from recipe amounts).
- [ ] **Free-text matching is still guesswork** for words without a rule (e.g. "jogurt", "leib").
      `core/scoring.py:76` treats "the word appears inside the name" as a perfect match. Adding aliases or
      rules for the most common words would cover most lists.
- [ ] **Preferences live in one browser** (`localStorage`); they don't follow a tester to another device.
      Fine for validation.
- [ ] **No route or location yet** ("Rimi is 4 min off your route"). This was the original "NEXT" stage;
      only worth it if validation passes.
- [ ] **Coop** (now owns the former Prisma stores, regional e-shops) is not covered. Lidl has no e-shop.

### 5. Technical debt (low priority)
- [ ] Old endpoints `POST /dinner` and `POST /optimize` are unused by the web app; remove them once
      nothing depends on them.
- [ ] Barbora searches run one at a time (it throttles parallel requests), so the first pricing of a dinner
      takes a few seconds; later requests are cached for 6 h (in memory, per process).
- [ ] The web app has no automated tests; it was checked by hand in headless Chrome.
- [ ] Scraping store sites is fragile and legally grey. Longer term: a data feed from toiduhind.ee or a retailer.

---

## Decisions already made (don't re-litigate)
- **Stores:** Selver, Rimi, Barbora (Barbora stands in for Maxima). Prisma closed. No Coop for now.
- **No AI with per-use cost.** Matching is rules + aliases. If AI is ever needed: self-hosted, fixed cost only.
- **Upkeep must stay side-hustle sized:** rules (query + category + words), never pinned product IDs; the
  health check is the only thing to watch.
- **Design:** receipt concept, fog / slate / lingonberry, Schibsted Grotesk + Martian Mono, top bar only,
  everything on one screen.

## Picking it up again
```bash
docker compose up --build -d                 # app at http://localhost:8000/?u=yourname
python -m pytest -q tests                    # 61 tests
python -m scripts.healthcheck                # are the stores and rules still OK?
docker compose exec db psql -U groceries     # look at events (queries in README.md)
```

**Suggested first session back:** write the kill criteria, deploy with a database, then recruit the first 10 testers.
