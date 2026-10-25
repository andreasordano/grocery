-- WEB-17: events logged before the app marked internal people. The founder (tester link "andrea", or the
-- name "andrea" typed on a device) and Claude's checks ("claude…", "internal-…") get internal = true,
-- everyone else false, so metric views can filter on data->>'internal'. New events carry it already.
UPDATE events SET data = COALESCE(data, '{}'::jsonb) || '{"internal": true}'::jsonb
WHERE NOT (COALESCE(data, '{}'::jsonb) ? 'internal')
  AND (lower(user_id) = 'andrea' OR user_id ILIKE 'claude%' OR user_id ILIKE 'internal-%'
       OR user_id IN (SELECT user_id FROM events WHERE type = 'hello' AND lower(trim(data->>'name')) = 'andrea'));

UPDATE events SET data = COALESCE(data, '{}'::jsonb) || '{"internal": false}'::jsonb
WHERE NOT (COALESCE(data, '{}'::jsonb) ? 'internal');
