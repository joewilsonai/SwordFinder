-- Enhanced MLB Pitches Table for SwordFinder
-- Includes all MLB fields plus custom sword scoring and percentile fields

-- Drop table if you want to recreate (BE CAREFUL!)
-- DROP TABLE IF EXISTS mlb_pitches_enhanced CASCADE;

-- Create enhanced MLB pitches table
CREATE TABLE IF NOT EXISTS mlb_pitches_enhanced (
    -- Primary key
    id BIGSERIAL PRIMARY KEY,
    
    -- Basic game info
    game_pk BIGINT,
    game_date DATE,
    game_type VARCHAR(10),
    game_year INTEGER,
    home_team VARCHAR(5),
    away_team VARCHAR(5),
    
    -- Pitch info
    pitch_type VARCHAR(10),
    pitch_name VARCHAR(50),
    pitch_number INTEGER,
    at_bat_number INTEGER,
    
    -- Player info
    pitcher INTEGER,
    pitcher_name VARCHAR(100),
    batter INTEGER,
    player_name VARCHAR(100),
    stand VARCHAR(1),
    p_throws VARCHAR(1),
    
    -- Count/situation
    balls INTEGER,
    strikes INTEGER,
    outs_when_up INTEGER,
    inning INTEGER,
    inning_topbot VARCHAR(10),
    on_1b BOOLEAN,
    on_2b BOOLEAN,
    on_3b BOOLEAN,
    
    -- Pitch metrics
    release_speed REAL,
    effective_speed REAL,
    release_spin_rate REAL,
    release_extension REAL,
    release_pos_x REAL,
    release_pos_y REAL,
    release_pos_z REAL,
    
    -- Movement
    pfx_x REAL,
    pfx_z REAL,
    plate_x REAL,
    plate_z REAL,
    
    -- Hit metrics
    events VARCHAR(50),
    description VARCHAR(50),
    hit_location INTEGER,
    hit_distance_sc REAL,
    launch_speed REAL,
    launch_angle REAL,
    launch_speed_angle REAL,
    hc_x REAL,
    hc_y REAL,
    
    -- Zone info
    zone INTEGER,
    type VARCHAR(1),
    
    -- Bat tracking (2025 new!)
    bat_speed REAL,
    swing_length REAL,
    swing_path_tilt REAL,
    attack_angle REAL,
    
    -- Custom sword finder fields
    sword_score REAL,
    is_sword_candidate BOOLEAN DEFAULT FALSE,
    is_true_sword BOOLEAN DEFAULT FALSE,
    video_azure_blob_url TEXT,
    video_processed_at TIMESTAMP,
    
    -- Percentile fields (calculated later)
    velo_percentile_overall REAL,
    velo_percentile_pitch_type REAL,
    spin_percentile_overall REAL,
    spin_percentile_pitch_type REAL,
    movement_percentile_overall REAL,
    movement_percentile_pitch_type REAL,
    extension_percentile_overall REAL,
    extension_percentile_pitch_type REAL,
    
    -- For sword swings specifically
    bat_speed_percentile_sword REAL,
    swing_tilt_percentile_sword REAL,
    pitch_nastiness_percentile REAL,
    
    -- Helper flags
    is_home_run BOOLEAN DEFAULT FALSE,
    is_strikeout BOOLEAN DEFAULT FALSE,
    is_walk BOOLEAN DEFAULT FALSE,
    is_hit BOOLEAN DEFAULT FALSE,
    is_whiff BOOLEAN DEFAULT FALSE,
    has_bat_tracking BOOLEAN DEFAULT FALSE,
    
    -- MLB play ID for video retrieval
    mlb_play_id VARCHAR(100),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- All other MLB fields as JSONB for flexibility
    additional_data JSONB
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_game_pk ON mlb_pitches_enhanced(game_pk);
CREATE INDEX IF NOT EXISTS idx_pitcher ON mlb_pitches_enhanced(pitcher);
CREATE INDEX IF NOT EXISTS idx_batter ON mlb_pitches_enhanced(batter);
CREATE INDEX IF NOT EXISTS idx_game_date ON mlb_pitches_enhanced(game_date);
CREATE INDEX IF NOT EXISTS idx_events ON mlb_pitches_enhanced(events);
CREATE INDEX IF NOT EXISTS idx_pitch_type ON mlb_pitches_enhanced(pitch_type);
CREATE INDEX IF NOT EXISTS idx_is_sword ON mlb_pitches_enhanced(is_sword_candidate);
CREATE INDEX IF NOT EXISTS idx_is_true_sword ON mlb_pitches_enhanced(is_true_sword);
CREATE INDEX IF NOT EXISTS idx_release_speed ON mlb_pitches_enhanced(release_speed);
CREATE INDEX IF NOT EXISTS idx_bat_speed ON mlb_pitches_enhanced(bat_speed);
CREATE INDEX IF NOT EXISTS idx_sword_score ON mlb_pitches_enhanced(sword_score);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_pitcher_pitch_type ON mlb_pitches_enhanced(pitcher, pitch_type);
CREATE INDEX IF NOT EXISTS idx_game_date_events ON mlb_pitches_enhanced(game_date, events);

-- Sample queries after data is loaded:
/*
-- Find worst sword swings
SELECT * FROM mlb_pitches_enhanced 
WHERE is_true_sword = TRUE 
ORDER BY bat_speed ASC 
LIMIT 10;

-- Find fastest pitches by type
SELECT pitch_type, MAX(release_speed) as max_velo, COUNT(*) as count
FROM mlb_pitches_enhanced
WHERE release_speed IS NOT NULL
GROUP BY pitch_type
ORDER BY max_velo DESC;

-- Find longest home runs by month
SELECT 
    DATE_TRUNC('month', game_date) as month,
    MAX(hit_distance_sc) as longest_hr,
    player_name
FROM mlb_pitches_enhanced
WHERE is_home_run = TRUE
GROUP BY month, player_name
ORDER BY month, longest_hr DESC;
*/ 