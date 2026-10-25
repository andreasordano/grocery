-- The last answer to each store search (core/fetch.py), so a restart or wake-up starts with a warm cache
-- instead of asking every store again. Written by the price log's writer; read once at startup.
CREATE TABLE IF NOT EXISTS search_cache (
    retailer TEXT NOT NULL,
    query TEXT NOT NULL,                -- lower-cased, trimmed
    fetched_at TIMESTAMPTZ NOT NULL,
    products JSONB NOT NULL,            -- the connector's answer, as cached
    PRIMARY KEY (retailer, query)
);
CREATE INDEX IF NOT EXISTS search_cache_fetched_idx ON search_cache (fetched_at);
ALTER TABLE search_cache ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON search_cache FROM anon, authenticated;
    END IF;
END
$$;
