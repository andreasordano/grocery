-- How to cook a dinner and a link to its recipe page (WEB-34): optional, written by the person,
-- and copied into the snapshot when a dinner is sent. Existing rows keep NULL.
ALTER TABLE my_dinners ADD COLUMN IF NOT EXISTS method TEXT;
ALTER TABLE my_dinners ADD COLUMN IF NOT EXISTS link TEXT;
ALTER TABLE shares ADD COLUMN IF NOT EXISTS method TEXT;
ALTER TABLE shares ADD COLUMN IF NOT EXISTS link TEXT;
