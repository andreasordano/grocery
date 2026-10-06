# pantryrun: project status and next steps

_Last updated: 7 October 2026. Written to pick the project up again later._
_Code: branch `better-search-and-dishes` (pushed, not yet merged into `main`)._

**Thesis:** "Don't compare groceries. Decide what to do." Someone leaving work picks a dinner and gets
**one store and a shopping list** ("Go to Barbora: 5,92 €"), not a price spreadsheet.

**The question that matters:** will normal people use this to make grocery decisions **repeatedly**?
Not "can it compare prices"; that already works, and [toiduhind.ee](https://toiduhind.ee) does it for free.

---

## Where we are against the original plan

The plan was **30% engineering / 70% validation** over 2–4 weeks. So far it has been close to 100%
engineering: the app is far ahead of what validation needed. **One tester (from the founder's circle) has
tried it**; her feedback drove the search, dinner-ideas and quantity work below. **No testers from outside
that circle yet.** All 245 events in the local database are under one name (`andrea`), 5–6 Oct 2026.

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
- Postgres in Docker Compose, event log, tests, README.
- After the first tester (6–7 Oct): free-text matching that trusts the stores' shelves; suggestions while
  typing; product photos and shelves on the receipt; 355 NutriData dishes by category; quantities
  ("paprika 600g"); people's own dinners ("Mine"); sending a dinner by link; renamed to **pantryrun** with
  a typographic logo ("pantry" upright, "run" italic).

---

## Missing, in priority order

### 1. Validation (the actual next step)
- [ ] **Write the kill criteria now**, before anyone tests. Draft:
      - 20–30 testers who are not friends, 2 weeks.
      - **Continue** if ≥ 30% make a second request **without being prompted** within 7 days, and ≥ 40% of
        recommendations get "I'll go there".
      - **Stop or rethink** if < 25% come back unprompted.
- [ ] **10 interviews** about past behaviour, not the idea. Expect "I go to the closest store"; that answer matters.
- [ ] **Recruit testers**: Estonian Facebook groups, r/Eesti, office chats. Give each a **unique** personal
      link (`/?u=anna-k7`): own dinners are stored under that name and there are no passwords.
- [ ] **Put the app online** so testers can reach it (see Deployment). Or run the concierge version by hand
      over chat first and use the app as a back-office tool.
- [ ] **Test the second framing**, "this week's offers → 3 dinners": weekly, habit-forming, and something
      ChatGPT can't answer. It needs campaign data (flyers / offer pages), which we don't collect yet.
- [ ] **Shelf-price check**: ~25 ingredients, physical store vs e-shop. If the gap is under 5–10% outside
      campaigns, e-shop prices are good enough.

### 2. Deployment (blocks real users)
- [ ] **Merge `better-search-and-dishes` into `main`.**
- [ ] **Deploy somewhere.** `render.yaml` defines one service, `pantryrun-api`, which also serves the web app.
- [ ] **Add a Postgres database** and set `DATABASE_URL` on the API. Without it, events, people's own dinners
      and shared links go to SQLite on Render's disk and are **lost on every deploy**.
- [ ] Optional: rename the GitHub repository (`grocery` → `pantryrun`) and pick a domain.
- [ ] **Run the health-check workflow once on GitHub** ("Run workflow"). It has never run there, and store
      sites might block GitHub's servers.
- [ ] Note: GitHub turns scheduled workflows off after 60 days without repository activity.

### 3. Product direction agreed on 6 Oct 2026 (in progress)
- [x] **Show discounts** on the receipt (regular price, % off, offer end date, card price, multi-buy notes, "You save").
- [x] **Pantry items can be added** to a dinner trip (tap "õli" under "Have at home").
- [ ] **One list with Ideas:** merge Dinner and Shopping list. Free items are the core; recipes become ideas
      that add their ingredients to the list as editable items. No new hand-written recipes.
- [x] **My dinners:** people write their own dinners (Dinner → Mine), stored per personal link in the
      `my_dinners` table. Not yet: saving a shopping list as a dinner, or copying and editing a NutriData dish.
      Personal links must be unique (`/?u=anna-k7`): there are no passwords.
- [x] **Send a dinner by link** (`/?dinner=…`): the receiver sees it priced for them and can save it.
      Watch `share_created` → `share_opened` → `my_dinner_saved` (from_share): do dinners get passed along?
- [ ] Later, with real users: "Popular this week" from the event log (anonymous counts, no moderation).
      A public feed of people's dinners only after accounts exist.
- [x] **NutriData dinners:** 355 dishes from the state food database (tka.nutridata.ee) in six categories,
      generated by `scripts/import_nutridata.py`; Dinner screen has category chips, 8 random dishes and
      "Show me others". See README "NutriData dishes".
- [ ] **Ask TAI (Tervise Arengu Instituut) whether reuse with attribution is allowed** before a public launch;
      NutriData publishes no explicit terms. The app already credits them on the Dinner screen.
- [ ] **Known rough edges in dishes:** NutriData's grouping puts a few odd dishes in categories (Burrito and
      Ahjupannkook under Fish); a first price of a dish with many free-text ingredients can take 5–20 s while
      Barbora answers one request at a time (cached for 6 h after); small amounts are priced as whole packs
      (20 g ginger → a 200 g jar); free text can still pick a related product over the thing itself
      ("veiseliha" → a beef stock cube at Rimi). Watch `dinner_category` / `dinner_shuffle` events to see if
      categories get used.
- [ ] **Featured ideas from discounts**, computed automatically ("Shakshuka is 30% cheaper at Rimi this week").
      Later the slot for store-paid placement, always labelled.

### 4. Product gaps found while testing
- [x] **Quantities in the shopping list** ("paprika 600g", "2 piim", "kartul 2kg"), typed or changed by tapping
      an item. See README "Quantities". Not yet: changing amounts on dinner lines ("need 80 g" → 150 g).
- [x] **Free-text matching** (6 Oct 2026, after the first tester's feedback): word forms ("with X" / "of X" /
      the thing itself), a per-store shelf vote and a singular retry. "maapähklivõi" now finds peanut butter at
      all three stores instead of a Reese's bar; "tee" no longer picks cat litter, "või" no longer picks
      mashed potato *with* butter. See README "Free-text items".
- [x] **Suggestions while typing** from a word list built from Selver's catalog (`python -m scripts.build_vocab`,
      re-run every month or two). The receipt shows the store shelf, and the picker shows product photos.
- [ ] **Watch `item_added` events:** do testers pick suggestions (`via: "suggestion"`) or type freely?
- [ ] **Preferences live in one browser** (`localStorage`); they don't follow a tester to another device.
      Fine for validation.
- [ ] **No route or location yet** ("Rimi is 4 min off your route"). This was the original "NEXT" stage;
      only worth it if validation passes.
- [ ] **Coop** (now owns the former Prisma stores, regional e-shops) is not covered. Lidl has no e-shop.

### 5. Technical debt (low priority)
- [x] Old endpoints removed (7 Oct): `POST /dinner`, `POST /optimize`, `POST /availability`, with
      `core/optimiser.py` and `catalog.list_offers`. `diagram.md` rewritten for the current architecture.
- [x] Slow first pricing (7 Oct): the API warms the cache for every ingredient rule's searches at startup
      (~22 s in the background) and refreshes them before they expire. Classic dinners then price in under
      0.1 s; NutriData dishes with free-text ingredients still take a second or two on first use.
      `CACHE_WARMUP=0` turns it off. The cache is still in memory, per process.
- [x] Browser tests for the web page (7 Oct): `tests/e2e` (Playwright, fake stores) cover the name prompt,
      a list with amounts, editing an item, suggestions, own dinners, sending a dinner, broken links and phone
      width. CI now also runs on pull requests (tests only, no deploy).
- [ ] Scraping store sites is fragile and legally grey. Next step: ask toiduhind.ee (or a retailer) whether
      a data feed is possible, before there are many users.

---

## Decisions already made (don't re-litigate)
- **Stores:** Selver, Rimi, Barbora (Barbora stands in for Maxima). Prisma closed. No Coop for now.
- **Name:** pantryrun. Wordmark "pantry" upright + "run" italic + lingonberry full stop; icon "pr.".
- **No AI with per-use cost.** Matching is rules + aliases, then free-text matching with a shelf vote.
  If AI is ever needed: self-hosted, fixed cost only.
- **No accounts during validation:** people are the name in their personal link; own dinners are stored
  under it. Real sign-in only after validation passes. Sharing is by private link, not a public feed.
- **Upkeep must stay side-hustle sized:** rules (query + category + words), never pinned product IDs; the
  health check is the only thing to watch.
- **Design:** receipt concept, fog / slate / lingonberry, Schibsted Grotesk + Martian Mono, top bar only,
  everything on one screen.

## Picking it up again
```bash
docker compose up --build -d                 # app at http://localhost:8000/?u=yourname
python -m pytest -q tests                    # 94 tests (+7 browser tests with requirements-dev.txt)
python -m scripts.healthcheck                # are the stores and rules still OK?
docker compose exec db psql -U groceries     # look at events (queries in README.md)
```

**Suggested first session back:** write the kill criteria, deploy with a database, then recruit the first 10 testers.
