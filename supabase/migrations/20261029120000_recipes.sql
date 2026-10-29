-- WEB-53: pantryrun's own dinners, edited in /admin.html (core/recipes.py). Ids are stable ("pr-…") and never
-- reused: a dinner is archived, not deleted, so the events that name it (basket recipe_ids, dinner_view, …)
-- keep pointing at it. Only published dinners reach the app.
--   ingredients: typed items for `servings` people ("400 g räimefilee"), priced like a pasted list
--   pantry:      assumed at home
--   tags:        chip ids from data/dinner_chips.yaml; "quick" and "seasonal" are never stored (minutes, months)
--   brand/label: a partner collection ("With Santa Maria"); NULL for pantryrun's own
--   rights:      where the recipe and its photo may be used from
CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY CHECK (id ~ '^pr-[a-z0-9-]+$'),
    name TEXT NOT NULL CHECK (name <> ''),
    about TEXT,
    method TEXT,
    emoji TEXT,
    image TEXT,
    servings INT NOT NULL DEFAULT 4 CHECK (servings BETWEEN 1 AND 12),
    minutes INT CHECK (minutes > 0),
    ingredients TEXT[] NOT NULL DEFAULT '{}',
    pantry TEXT[] NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    months INT[] NOT NULL DEFAULT '{}',
    brand TEXT,
    label TEXT,
    rights TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    review_by DATE,
    notes TEXT,                 -- the owner's, never shown in the app
    created TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS recipes_status_idx ON recipes (status);
ALTER TABLE recipes ENABLE ROW LEVEL SECURITY;

-- How each dinner is used, by its id: every kind of dinner (pantryrun's, Rimi's "rm-…", the classics, people's
-- own "my-…"), testers only, as the other metrics. answers: baskets it was priced in; people: who got those;
-- copies: "Make it yours"; cooked: "Did you cook it?" yes from the newsletter.
CREATE OR REPLACE VIEW metrics.dinner_usage AS
WITH uses AS (
    SELECT e.ts, e.type, e.user_id, d.id
    FROM public.events e
    JOIN metrics.testers t ON t.user_id = e.user_id
    CROSS JOIN LATERAL (
        SELECT jsonb_array_elements_text(e.data->'recipe_ids') AS id WHERE e.type = 'basket'
        UNION ALL SELECT e.data->>'recipe_id' WHERE e.type = 'basket' AND NOT (e.data ? 'recipe_ids')
        UNION ALL SELECT e.data->>'id' WHERE e.type = 'dinner_view'
        UNION ALL SELECT e.data->>'from' WHERE e.type = 'dinner_copy'
        UNION ALL SELECT e.data->>'dinner' WHERE e.type = 'cooked' AND e.data->>'answer' = 'yes'
    ) d
    WHERE e.type IN ('basket', 'dinner_view', 'dinner_copy', 'cooked') AND d.id IS NOT NULL
)
SELECT id,
       count(*) FILTER (WHERE type = 'dinner_view') AS views,
       count(*) FILTER (WHERE type = 'basket') AS answers,
       count(DISTINCT user_id) FILTER (WHERE type = 'basket') AS people,
       count(*) FILTER (WHERE type = 'dinner_copy') AS copies,
       count(*) FILTER (WHERE type = 'cooked') AS cooked,
       max(ts) AS last_used
FROM uses
GROUP BY id;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN  -- Supabase only, not local Postgres
        REVOKE ALL ON recipes FROM anon, authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst') THEN  -- DATA-5
        GRANT SELECT ON recipes TO analyst;
        CREATE POLICY analyst_reads ON recipes FOR SELECT TO analyst USING (true);
        GRANT SELECT ON metrics.dinner_usage TO analyst;
    END IF;
END
$$;
