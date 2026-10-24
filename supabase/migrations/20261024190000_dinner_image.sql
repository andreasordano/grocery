-- A dinner's photo (WEB-35): the photo URL of the recipe page it was made from, hotlinked, never
-- copied. Optional and copied into sent dinners. Until this has run, the app saves dinners
-- without their photo (core/my_dinners.py checks for the column).
ALTER TABLE my_dinners ADD COLUMN IF NOT EXISTS image TEXT;
ALTER TABLE shares ADD COLUMN IF NOT EXISTS image TEXT;
