-- DATA-5: a read-only role for analysis tools (pgweb, Metabase), so looking at data can never change it.
-- The role can't log in. Each person or tool gets its own login that is a member, made by hand in
-- Supabase's SQL editor so no password is ever in the repo:
--   CREATE ROLE andrea_read LOGIN PASSWORD '<a long random one>' IN ROLE analyst;
-- Connect through the session pooler as user "andrea_read.<project ref>".
-- Later, partner-private tables must be left out of these grants (DATA-4).

DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public, metrics TO analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA public, metrics TO analyst;
ALTER DEFAULT PRIVILEGES IN SCHEMA metrics GRANT SELECT ON TABLES TO analyst;

-- The tables have row-level security with no policies; this lets the analyst read every row, nothing else.
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['events', 'my_dinners', 'shares', 'nudges',
                             'collection_runs', 'retailer_products', 'price_observations'] LOOP
        IF to_regclass('public.' || t) IS NOT NULL
           AND NOT EXISTS (SELECT FROM pg_policies WHERE schemaname = 'public' AND tablename = t
                                                      AND policyname = 'analyst_reads') THEN
            EXECUTE format('CREATE POLICY analyst_reads ON public.%I FOR SELECT TO analyst USING (true)', t);
        END IF;
    END LOOP;
END $$;
