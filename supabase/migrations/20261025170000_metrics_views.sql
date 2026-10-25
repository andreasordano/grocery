-- DATA-6: the validation metrics as views, one definition each, in the schema "metrics".
-- Definitions follow Confluence → Validation → "Kill criteria and metrics". Internal people (the founder,
-- Claude's checks) are left out everywhere: anyone with even one event marked internal.
-- Days are Tallinn days. Views run as their owner, so the analyst role (DATA-5) reads them without RLS policies.

-- PROD-5: every reminder sent to a tester (by hand, or a newsletter edition), so "unprompted" can be measured.
CREATE TABLE IF NOT EXISTS nudges (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL,      -- whatsapp | email | newsletter | in_person | …
    note TEXT
);
CREATE INDEX IF NOT EXISTS nudges_user_ts_idx ON nudges (user_id, ts);
ALTER TABLE nudges ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN  -- Supabase only, not local Postgres
        REVOKE ALL ON nudges FROM anon, authenticated;
        REVOKE ALL ON SEQUENCE nudges_id_seq FROM anon, authenticated;
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS metrics;
SET search_path TO metrics, public;

-- One row per person: when they first came and first got an answer, whether they're internal,
-- their name and the store they usually shop at (latest answer).
CREATE OR REPLACE VIEW people AS
SELECT user_id,
       min(ts) AS first_seen,
       min(ts) FILTER (WHERE type = 'basket') AS first_answer,
       bool_or(COALESCE((data->>'internal')::boolean, false)
               OR lower(user_id) = 'andrea' OR user_id ILIKE 'claude%' OR user_id ILIKE 'internal-%') AS internal,
       (array_agg(data->>'name' ORDER BY ts DESC) FILTER (WHERE type = 'hello'))[1] AS name,
       (array_agg(data->>'store' ORDER BY ts DESC) FILTER (WHERE type = 'usual_store'))[1] AS usual_store
FROM events
WHERE COALESCE(user_id, '') <> ''
GROUP BY user_id;

-- The people every metric counts.
CREATE OR REPLACE VIEW testers AS
SELECT * FROM people WHERE NOT internal;

-- Every answer (basket event) a tester got. viable_stores: stores that could make the whole basket.
-- came_from: the "from" of the tester's latest visit before the answer (tester_link, newsletter, …).
CREATE OR REPLACE VIEW answers AS
SELECT e.id, e.ts, (e.ts AT TIME ZONE 'Europe/Tallinn')::date AS day, e.user_id,
       e.data->>'result_id' AS result_id,
       e.data->>'mission' AS mission,
       NULLIF(e.data->>'latency_s', '')::numeric AS latency_s,
       e.data->>'recommended_store' AS recommended_store,
       v.viable_stores, v.best_total, v.second_total,
       vis.came_from
FROM events e
JOIN testers t ON t.user_id = e.user_id
CROSS JOIN LATERAL (
    SELECT count(*) AS viable_stores, min(total) AS best_total, (array_agg(total ORDER BY total))[2] AS second_total
    FROM (SELECT (b->>'total_price')::numeric AS total
          FROM jsonb_array_elements(COALESCE(e.data->'baskets', '[]'::jsonb)) b
          WHERE COALESCE(b->>'status', 'ok') = 'ok' AND COALESCE(b->>'total_price', '') <> '') s
) v
LEFT JOIN LATERAL (
    SELECT x.data->>'from' AS came_from FROM events x
    WHERE x.type = 'visit' AND x.user_id = e.user_id AND x.ts <= e.ts
    ORDER BY x.ts DESC LIMIT 1
) vis ON true
WHERE e.type = 'basket';

-- Activation: testers who got at least one answer.
CREATE OR REPLACE VIEW activation AS
SELECT count(*) AS testers,
       count(first_answer) AS activated,
       round(count(first_answer)::numeric / NULLIF(count(*), 0), 3) AS share
FROM testers;

-- PRIMARY: unprompted return within 7 days. Per activated tester: another answer on a later day within
-- 7 days of the first, before any reminder (nudges) and not from a newsletter link.
-- window_complete: the 7 days are over, so the row can count.
CREATE OR REPLACE VIEW return_7d AS
SELECT t.user_id, t.name, t.first_answer, n.first_nudge,
       t.first_answer <= now() - interval '7 days' AS window_complete,
       EXISTS (SELECT 1 FROM answers a
               WHERE a.user_id = t.user_id
                 AND a.day > (t.first_answer AT TIME ZONE 'Europe/Tallinn')::date
                 AND a.ts < t.first_answer + interval '7 days'
                 AND (n.first_nudge IS NULL OR a.ts < n.first_nudge)
                 AND COALESCE(a.came_from, '') <> 'newsletter') AS returned_unprompted,
       EXISTS (SELECT 1 FROM answers a
               WHERE a.user_id = t.user_id
                 AND a.day > (t.first_answer AT TIME ZONE 'Europe/Tallinn')::date
                 AND a.ts < t.first_answer + interval '7 days') AS returned_any
FROM testers t
LEFT JOIN (SELECT user_id, min(ts) AS first_nudge FROM nudges GROUP BY user_id) n ON n.user_id = t.user_id
WHERE t.first_answer IS NOT NULL;

-- The kill-criteria number and its band (40% or more continue, 15% or less stop, in between extend).
CREATE OR REPLACE VIEW return_7d_band AS
SELECT count(*) AS activated_complete,
       count(*) FILTER (WHERE returned_unprompted) AS returned,
       round(count(*) FILTER (WHERE returned_unprompted)::numeric / NULLIF(count(*), 0), 3) AS share,
       CASE WHEN count(*) = 0 THEN 'NO DATA YET'
            WHEN count(*) FILTER (WHERE returned_unprompted)::numeric / count(*) >= 0.40 THEN 'CONTINUE'
            WHEN count(*) FILTER (WHERE returned_unprompted)::numeric / count(*) <= 0.15 THEN 'STOP OR RETHINK'
            ELSE 'EXTEND TO 50 TESTERS' END AS band
FROM return_7d
WHERE window_complete;

-- Acceptance: answers with an "I'll go to <store>" / all answers.
CREATE OR REPLACE VIEW acceptance AS
SELECT count(*) AS answers,
       count(*) FILTER (WHERE accepted) AS accepted,
       round(count(*) FILTER (WHERE accepted)::numeric / NULLIF(count(*), 0), 3) AS share
FROM (SELECT a.result_id,
             EXISTS (SELECT 1 FROM events x WHERE x.type = 'accept' AND x.data->>'result_id' = a.result_id) AS accepted
      FROM answers a) s;

-- Store switch: accepted answers whose store isn't the tester's usual store at that moment.
-- Barbora's prices stand for Maxima (WEB-25). Accepts without a known usual store (or "other") don't count.
CREATE OR REPLACE VIEW store_switch AS
SELECT count(*) AS accepts_with_usual_store,
       count(*) FILTER (WHERE store <> usual_store) AS switched,
       round(count(*) FILTER (WHERE store <> usual_store)::numeric / NULLIF(count(*), 0), 3) AS share
FROM (SELECT CASE e.data->>'store' WHEN 'barbora' THEN 'maxima' ELSE e.data->>'store' END AS store,
             (SELECT u.data->>'store' FROM events u
              WHERE u.type = 'usual_store' AND u.user_id = e.user_id AND u.ts <= e.ts
              ORDER BY u.ts DESC LIMIT 1) AS usual_store
      FROM events e JOIN testers t ON t.user_id = e.user_id
      WHERE e.type = 'accept') s
WHERE usual_store IS NOT NULL AND usual_store <> 'other';

-- No result: answers where no store could make the whole basket.
CREATE OR REPLACE VIEW no_result AS
SELECT count(*) AS answers,
       count(*) FILTER (WHERE viable_stores = 0) AS no_result,
       round(count(*) FILTER (WHERE viable_stores = 0)::numeric / NULLIF(count(*), 0), 3) AS share
FROM answers;

-- Answer time in seconds: median and the slowest 10%.
CREATE OR REPLACE VIEW answer_time AS
SELECT count(latency_s) AS answers,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_s) AS median_s,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY latency_s) AS p90_s
FROM answers;

-- Best vs second-best store: what choosing the store is worth, per answer with at least two viable stores.
CREATE OR REPLACE VIEW store_gap AS
SELECT count(*) AS answers,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY second_total - best_total) AS median_gap_eur,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY (second_total - best_total) / NULLIF(best_total, 0)) AS median_gap_share
FROM answers
WHERE second_total IS NOT NULL;

-- Entry point: what people asked for (one dinner, several dinners, a list).
CREATE OR REPLACE VIEW entry_point AS
SELECT mission, count(*) AS answers, count(DISTINCT user_id) AS testers
FROM answers
GROUP BY mission;

-- Weekly cohorts: testers by the week of their first answer, and how many got an answer in each week after.
CREATE OR REPLACE VIEW weekly_cohorts AS
SELECT date_trunc('week', t.first_answer AT TIME ZONE 'Europe/Tallinn')::date AS cohort_week,
       (date_trunc('week', a.ts AT TIME ZONE 'Europe/Tallinn')::date
        - date_trunc('week', t.first_answer AT TIME ZONE 'Europe/Tallinn')::date) / 7 AS week_n,
       count(DISTINCT a.user_id) AS active_testers
FROM testers t JOIN answers a ON a.user_id = t.user_id
GROUP BY 1, 2;

RESET search_path;
