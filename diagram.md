Here's the full application flow:

Summary of the architecture
1. Streamlit Frontend (app.py) — Users type generic item names via Quick Add, select which stores to search, and hit "Find best cart". The request is sent as a POST /optimize to the backend.

2. FastAPI Backend (api/service.py) — Receives {items, stores}, tokenizes keywords, then delegates to two core modules: fetch and optimize.

3. Fetching Layer (core/fetch.py) — For every item × store combination:

    - Builds multiple search queries (synonyms, token fallbacks)
    - Checks a TTL cache (core/cache.py) before calling external APIs
    - Normalizes raw results (price parsing, weight/volume extraction)
    - Scores and filters candidates (relevance ≥ 1, score ≤ 5), keeping top N per store

4. Store API Modules — Each store has its own adapter with a different integration method:

    * selver_api.py — Elasticsearch POST
    * barbora_api.py — REST GET
    * rimi_api.py — HTML scraping (BeautifulSoup)
    * prisma_api.py — GraphQL query
    
    Store dispatching is handled dynamically via stores_config.py (get_fetcher() does a runtime import).

5. Scoring (core/scoring.py) — Each candidate gets a composite score: unit_price + relevance_penalty + size_penalty (lower = better).

6. Optimizer (core/optimiser.py) — For each item, picks the product with the lowest score from valid stores → assembles the best cart.

7. Results display — Back in Streamlit: store comparison table, top candidates per item with score breakdowns, and the final best cart with total price.


# Application Architecture

```mermaid
flowchart TD

    %% ── STEP 1: UI ───────────────────────────────────────────
    subgraph UI["🖥️ 1 · Streamlit Frontend  (app.py)"]
        direction LR
        A["User types item names\n+ selects stores"] -->|"POST /optimize\n{items, stores}"| B["FastAPI Backend"]
    end

    %% ── STEP 2: API ──────────────────────────────────────────
    subgraph API["⚡ 2 · FastAPI Backend  (api/service.py)"]
        B --> B1["Tokenize keywords"]
        B1 --> B2["fetch_all()"]
        B2 --> B3["optimize_cart()"]
    end

    %% ── STEP 3: FETCH ────────────────────────────────────────
    subgraph FETCH["📦 3 · Fetching Layer  (core/fetch.py)    —    runs for every item × store"]
        direction LR
        B2 --> C1["Build queries\nsynonyms + fallbacks"]
        C1 --> C2{"TTL Cache\nhit?"}
        C2 -->|"HIT"| C4
        C2 -->|"MISS"| C3["Call store adapter\nvia get_fetcher()"]
        C3 --> C3b["Store APIs"]
        C3b --> C4["Normalize result\nprice · weight · volume"]
        C4 --> C5["Score candidate\ncore/scoring.py"]
        C5 --> C6["Filter\nrelevance ≥ 1  score ≤ 5\nkeep top N per store"]
    end

    %% ── STEP 3a: STORE ADAPTERS ──────────────────────────────
    subgraph C3b["🏪 Store Adapters  (dispatched by stores_config.py)"]
        direction LR
        S1["Selver\nElasticsearch"]
        S2["Barbora\nREST GET"]
        S3["Rimi\nHTML scrape"]
        S4["Prisma\nGraphQL"]
    end

    %% ── STEP 3b: SCORING ─────────────────────────────────────
    subgraph SCORING["📊 core/scoring.py"]
        direction LR
        SC["unit_price\n+ relevance_penalty\n+ size_penalty\n─────────────\n→ final score\n(lower = better)"]
    end
    C5 -.- SCORING

    %% ── STEP 4: OPTIMIZER ────────────────────────────────────
    subgraph OPT["🧮 4 · Optimizer  (core/optimiser.py)"]
        direction LR
        C6 -->|"all_products"| O1["Per item: pick product\nwith lowest score"]
        O1 --> O2["Assemble best_cart\ntotal_score · total_price"]
    end

    %% ── STEP 5: RESULTS ──────────────────────────────────────
    subgraph RESULTS["📋 5 · Streamlit Results  (app.py)"]
        direction LR
        O2 -->|"JSON response"| R1["Store comparison\n(total per store, missing items)"]
        O2 --> R2["Top candidates per item\n(score breakdown)"]
        O2 --> R3["Best Cart\n+ Total price"]
    end

    %% ── STYLES ───────────────────────────────────────────────
    style UI      fill:#dbeafe,stroke:#3b82f6,stroke-width:2px
    style API     fill:#fef3c7,stroke:#f59e0b,stroke-width:2px
    style FETCH   fill:#dcfce7,stroke:#22c55e,stroke-width:2px
    style C3b     fill:#fce7f3,stroke:#ec4899,stroke-width:2px
    style SCORING fill:#f3e8ff,stroke:#a855f7,stroke-width:1px,stroke-dasharray:4
    style OPT     fill:#fefce8,stroke:#eab308,stroke-width:2px
    style RESULTS fill:#ccfbf1,stroke:#14b8a6,stroke-width:2px
```