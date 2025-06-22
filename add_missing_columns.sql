-- Add missing columns for SwordFinder
-- Project: Swordfinder (seagurfpitfslyxxxztw)
-- Run this in Supabase SQL Editor: https://app.supabase.com/project/seagurfpitfslyxxxztw/sql/new

-- Perceived velocity columns
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS perceived_velocity REAL,
ADD COLUMN IF NOT EXISTS perceived_velo_percentile_overall REAL,
ADD COLUMN IF NOT EXISTS perceived_velo_percentile_pitch_type REAL;

-- Strike zone distance column
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS strike_zone_distance_inches REAL;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_sword_score ON mlb_pitches_enhanced(sword_score) WHERE sword_score > 0;
CREATE INDEX IF NOT EXISTS idx_perceived_velocity ON mlb_pitches_enhanced(perceived_velocity) WHERE perceived_velocity IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_strike_zone_distance ON mlb_pitches_enhanced(strike_zone_distance_inches) WHERE strike_zone_distance_inches IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_video_url ON mlb_pitches_enhanced(video_azure_blob_url) WHERE video_azure_blob_url IS NOT NULL;

-- Verify columns were added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'mlb_pitches_enhanced' 
AND column_name IN ('perceived_velocity', 'perceived_velo_percentile_overall', 
                    'perceived_velo_percentile_pitch_type', 'strike_zone_distance_inches')
ORDER BY column_name; 