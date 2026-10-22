-- Price observation log (DATA-2): what the stores answered on every fresh search, append-only.
-- Idempotent, so the app can also run it against local Postgres (core/price_log.py).

CREATE TABLE IF NOT EXISTS collection_runs (
    id BIGSERIAL PRIMARY KEY,
    retailer TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- search (a cache miss) | refresh (cache warm-up)
    query TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,               -- ok | empty | http_error | parse_error | blocked | timeout
    http_status INTEGER,
    n_products INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS collection_runs_retailer_started_idx ON collection_runs (retailer, started_at);

CREATE TABLE IF NOT EXISTS retailer_products (
    retailer TEXT NOT NULL,
    retailer_product_id TEXT NOT NULL,  -- Selver sku, Barbora id, Rimi product code
    name TEXT NOT NULL,
    brand TEXT,
    ean TEXT,                           -- Selver only
    pack_qty NUMERIC,
    pack_unit TEXT,                     -- g | ml | pcs; NULL when the name gives no size
    sold_by TEXT NOT NULL,              -- pack | kg | l
    category_path TEXT,
    url TEXT,
    image_url TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    product_id BIGINT,                  -- matching across stores (DATA-13); never set by the log
    match_method TEXT,
    match_confidence REAL,
    match_status TEXT,
    PRIMARY KEY (retailer, retailer_product_id)
);
CREATE INDEX IF NOT EXISTS retailer_products_ean_idx ON retailer_products (ean) WHERE ean IS NOT NULL;

CREATE TABLE IF NOT EXISTS price_observations (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES collection_runs (id),
    retailer TEXT NOT NULL,
    retailer_product_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    price NUMERIC(10, 2),               -- public price; NULL when the store shows none (out of stock)
    regular_price NUMERIC(10, 2),       -- only when on sale
    card_price NUMERIC(10, 2),          -- loyalty-card price, when known
    promo_text TEXT,                    -- multi-buy offer, not counted in price
    promo_until DATE,
    unit_price NUMERIC(12, 4),          -- price per unit_basis, from our own size parsing
    unit_basis TEXT,                    -- kg | l | pcs
    availability TEXT NOT NULL,         -- in_stock | out_of_stock | unknown
    search_rank INTEGER,                -- 1 = the store's first result for the run's query
    FOREIGN KEY (retailer, retailer_product_id) REFERENCES retailer_products (retailer, retailer_product_id)
);
CREATE INDEX IF NOT EXISTS price_observations_product_idx
    ON price_observations (retailer, retailer_product_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS price_observations_observed_idx ON price_observations (observed_at);

-- Same protection as the other tables: Supabase's web API roles can read and write nothing.
ALTER TABLE collection_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE retailer_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_observations ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON collection_runs, retailer_products, price_observations FROM anon, authenticated;
        REVOKE ALL ON SEQUENCE collection_runs_id_seq, price_observations_id_seq FROM anon, authenticated;
    END IF;
END
$$;
