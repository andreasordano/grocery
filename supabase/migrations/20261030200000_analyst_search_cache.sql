-- DATA-5: the analyst can read search_cache too (it was left out when the table was made), so the stores'
-- last answers can be looked at from pgweb.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst')
       AND NOT EXISTS (SELECT FROM pg_policies WHERE schemaname = 'public' AND tablename = 'search_cache'
                                                  AND policyname = 'analyst_reads') THEN
        GRANT SELECT ON search_cache TO analyst;
        CREATE POLICY analyst_reads ON search_cache FOR SELECT TO analyst USING (true);
    END IF;
END
$$;
