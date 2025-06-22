-- Add missing strike zone columns
-- These define the top and bottom of the strike zone for each pitch

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS sz_top REAL,
ADD COLUMN IF NOT EXISTS sz_bot REAL;

-- sz_top: Top of the strike zone in feet (typically 3.5-4.0)
-- sz_bot: Bottom of the strike zone in feet (typically 1.5-2.0) 