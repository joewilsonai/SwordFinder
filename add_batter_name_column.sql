-- Add batter_name column for SwordFinder name display fix
-- Statcast raw data has player_name = pitcher's name but no batter_name field.
-- This column will be populated via MLB Stats API lookup in the backfill script.

ALTER TABLE mlb_pitches_enhanced
ADD COLUMN IF NOT EXISTS batter_name TEXT;

CREATE INDEX IF NOT EXISTS idx_batter_name ON mlb_pitches_enhanced(batter_name)
  WHERE batter_name IS NOT NULL;
