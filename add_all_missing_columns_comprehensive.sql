-- Add ALL missing columns for mlb_pitches_enhanced
-- Run this in Supabase SQL Editor to fix the upload error

-- Age columns (legacy versions)
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_bat_legacy FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_pit_legacy FLOAT;

-- New 2025 columns from the error message
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS n_priorpa_thisgame_player_at_bat INTEGER;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS intercept_ball_minus_batter_pos_y_inches FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS pitcher_days_until_next_game INTEGER;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS arm_angle FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS attack_direction FLOAT;

-- Win expectancy columns
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS bat_win_exp FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS fld_win_exp FLOAT;

-- Deprecated columns that might still be in the data
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS tfs_zulu_deprecated TIMESTAMP;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS spin_rate_deprecated FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS break_length_deprecated FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS api_break_x_batter_in FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS api_break_z_batter_in FLOAT;

-- Boolean sword candidate column
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS is_sword_candidate BOOLEAN;

-- Final verification - show total columns
SELECT COUNT(*) as total_columns 
FROM information_schema.columns 
WHERE table_name = 'mlb_pitches_enhanced';

-- Show recently added columns
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'mlb_pitches_enhanced' 
AND column_name IN ('age_bat', 'age_pit', 'age_bat_legacy', 'age_pit_legacy', 'is_sword_candidate')
ORDER BY column_name; 