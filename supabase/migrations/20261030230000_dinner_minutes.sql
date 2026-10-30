-- How long a dinner of one's own takes (WEB-51): typed in the editor, or read from a recipe link's data or a
-- pasted recipe that says it ("Valmistusaeg: 30 min"). Optional and copied into sent dinners, like the photo.
-- Run before deploying the code that saves it (core/my_dinners.py writes the column).
ALTER TABLE my_dinners ADD COLUMN IF NOT EXISTS minutes INT CHECK (minutes > 0);
ALTER TABLE shares ADD COLUMN IF NOT EXISTS minutes INT CHECK (minutes > 0);
