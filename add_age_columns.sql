-- Add missing age columns to mlb_pitches_enhanced table
-- Run this in Supabase SQL Editor

-- Add age_bat column (batter's age)
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_bat FLOAT;

-- Also add age_pit column (pitcher's age) if missing
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS age_pit FLOAT;

-- Check if columns were added successfully
SELECT 
    column_name, 
    data_type 
FROM 
    information_schema.columns 
WHERE 
    table_name = 'mlb_pitches_enhanced' 
    AND column_name IN ('age_bat', 'age_pit')
ORDER BY 
    column_name; 