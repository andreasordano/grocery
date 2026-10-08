-- The tables the app already uses (core/events.py, core/my_dinners.py), same columns as before,
-- so data copied from the Render database fits as-is.

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    user_id TEXT,
    session_id TEXT,
    type TEXT NOT NULL,
    data JSONB
);
CREATE INDEX IF NOT EXISTS events_ts_idx ON events (ts);
CREATE INDEX IF NOT EXISTS events_user_ts_idx ON events (user_id, ts);
CREATE INDEX IF NOT EXISTS events_type_ts_idx ON events (type, ts);

CREATE TABLE IF NOT EXISTS my_dinners (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    servings INTEGER NOT NULL,
    items JSONB NOT NULL,
    created TIMESTAMPTZ NOT NULL,
    updated TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS my_dinners_user_idx ON my_dinners (user_id);

CREATE TABLE IF NOT EXISTS shares (
    token TEXT PRIMARY KEY,
    user_id TEXT,
    recipe_id TEXT,
    name TEXT NOT NULL,
    servings INTEGER NOT NULL,
    items JSONB NOT NULL,
    pantry JSONB NOT NULL,
    created TIMESTAMPTZ NOT NULL
);

-- Supabase publishes the public schema through its web API (PostgREST). pantryrun doesn't use it:
-- the app connects as the database owner. Row-level security with no policies, plus revoked grants,
-- means the API's anon/authenticated roles can read and write nothing.
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE my_dinners ENABLE ROW LEVEL SECURITY;
ALTER TABLE shares ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON events, my_dinners, shares FROM anon, authenticated;
REVOKE ALL ON SEQUENCE events_id_seq, my_dinners_id_seq FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
