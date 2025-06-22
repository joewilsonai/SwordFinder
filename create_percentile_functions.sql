-- SQL Functions for Percentile Calculations
-- Run these in your Supabase SQL Editor

-- 1. Function to execute arbitrary SQL (for percentile updates)
CREATE OR REPLACE FUNCTION execute_sql(query text)
RETURNS void AS $$
BEGIN
    EXECUTE query;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Function to execute SQL and return results
CREATE OR REPLACE FUNCTION execute_sql_query(query text)
RETURNS json AS $$
DECLARE
    result json;
BEGIN
    EXECUTE 'SELECT array_to_json(array_agg(row_to_json(t))) FROM (' || query || ') t'
    INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 3. Add movement_total column if it doesn't exist
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS movement_total FLOAT;

-- 4. Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_release_speed ON mlb_pitches_enhanced(release_speed);
CREATE INDEX IF NOT EXISTS idx_release_spin_rate ON mlb_pitches_enhanced(release_spin_rate);
CREATE INDEX IF NOT EXISTS idx_bat_speed ON mlb_pitches_enhanced(bat_speed) WHERE bat_speed > 0;
CREATE INDEX IF NOT EXISTS idx_pitch_type ON mlb_pitches_enhanced(pitch_type);
CREATE INDEX IF NOT EXISTS idx_game_date ON mlb_pitches_enhanced(game_date);
CREATE INDEX IF NOT EXISTS idx_sword_score ON mlb_pitches_enhanced(sword_score) WHERE sword_score > 0;

-- 5. Create materialized view for distribution statistics (optional, for performance)
CREATE MATERIALIZED VIEW IF NOT EXISTS pitch_velocity_distributions AS
SELECT 
    pitch_type,
    PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY release_speed) as p1,
    PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY release_speed) as p5,
    PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY release_speed) as p10,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY release_speed) as p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY release_speed) as p50,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY release_speed) as p75,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY release_speed) as p90,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY release_speed) as p95,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY release_speed) as p99,
    COUNT(*) as count,
    AVG(release_speed) as mean,
    STDDEV(release_speed) as stddev
FROM mlb_pitches_enhanced
WHERE release_speed IS NOT NULL AND pitch_type IS NOT NULL
GROUP BY pitch_type
HAVING COUNT(*) >= 100;

-- 6. Function to refresh distribution cache
CREATE OR REPLACE FUNCTION refresh_distribution_cache()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW pitch_velocity_distributions;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 7. Grant execute permissions (adjust role as needed)
GRANT EXECUTE ON FUNCTION execute_sql(text) TO service_role;
GRANT EXECUTE ON FUNCTION execute_sql_query(text) TO service_role;
GRANT EXECUTE ON FUNCTION refresh_distribution_cache() TO service_role; 