-- Comprehensive column check and addition for mlb_pitches_enhanced
-- Run this in Supabase SQL Editor to ensure all columns exist

-- First, let's see what columns we currently have
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'mlb_pitches_enhanced'
ORDER BY column_name;

-- Add potentially missing columns based on pybaseball 2025 data
-- These are columns that might be in the data but missing from our table

-- Age columns
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_bat FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_pit FLOAT;

-- New 2025 bat tracking columns that might be missing
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS pitcher_days_until_next_game INTEGER;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS intercept_ball_minus_batter_pos_y_inches FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS arm_angle FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS attack_direction FLOAT;

-- Other potentially missing columns
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_bat_legacy FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_pit_legacy FLOAT;

-- Win expectancy columns
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS bat_win_exp FLOAT;

ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS fld_win_exp FLOAT;

-- Final check - count all columns
SELECT COUNT(*) as total_columns 
FROM information_schema.columns 
WHERE table_name = 'mlb_pitches_enhanced';

-- Show any columns with 'age' in the name
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'mlb_pitches_enhanced' 
AND column_name LIKE '%age%'
ORDER BY column_name; 