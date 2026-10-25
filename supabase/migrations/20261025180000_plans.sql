-- WEB-37: the dinners of each weekly newsletter edition (core/plans.py), opened with /?plan=<token>.
CREATE TABLE IF NOT EXISTS plans (
    token TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    dinners JSONB NOT NULL,     -- recipe ids, in order
    featured TEXT,              -- the one labelled "Featured", or NULL
    created TIMESTAMPTZ NOT NULL
);
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN  -- Supabase only, not local Postgres
        REVOKE ALL ON plans FROM anon, authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN  -- DATA-5
        GRANT SELECT ON plans TO analyst;
        CREATE POLICY analyst_reads ON plans FOR SELECT TO analyst USING (true);
    END IF;
END
$$;
