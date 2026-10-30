-- What a dinner of one's own takes from home (WEB-51): salt, spices, oil, listed under "From home" and not
-- priced, like pantryrun's own dinners. Sent dinners have had it since the start (shares.pantry).
-- Runs after the code is deployed: until then dinners are kept without it (core/my_dinners.py looks for it).
ALTER TABLE my_dinners ADD COLUMN IF NOT EXISTS pantry JSONB NOT NULL DEFAULT '[]';
