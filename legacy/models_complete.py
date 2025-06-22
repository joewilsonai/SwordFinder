"""
Complete database models for storing all 118 fields from authentic MLB Statcast data
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
import os
from contextlib import contextmanager

Base = declarative_base()

class StatcastPitch(Base):
    """
    Complete Statcast pitch data - stores all 118 fields from authentic MLB dataset
    """
    __tablename__ = 'statcast_pitches'

    id = Column(Integer, primary_key=True)
    
    # Core pitch identification
    pitch_type = Column(String(10))
    game_date = Column(String(20))
    release_speed = Column(Float)
    release_pos_x = Column(Float)
    release_pos_z = Column(Float)
    player_name = Column(String(100))
    batter = Column(Integer)
    pitcher = Column(Integer)
    events = Column(String(100))
    description = Column(String(100))
    
    # Spin and break (legacy)
    spin_dir = Column(Float)
    spin_rate_deprecated = Column(Float)
    break_angle_deprecated = Column(Float)
    break_length_deprecated = Column(Float)
    
    # Zone and game context
    zone = Column(Integer)
    des = Column(Text)
    game_type = Column(String(10))
    stand = Column(String(5))
    p_throws = Column(String(5))
    home_team = Column(String(10))
    away_team = Column(String(10))
    type = Column(String(5))
    hit_location = Column(Integer)
    bb_type = Column(String(20))
    balls = Column(Integer)
    strikes = Column(Integer)
    game_year = Column(Integer)
    
    # Pitch movement and location
    pfx_x = Column(Float)
    pfx_z = Column(Float)
    plate_x = Column(Float)
    plate_z = Column(Float)
    
    # Baserunners
    on_3b = Column(Integer)
    on_2b = Column(Integer)
    on_1b = Column(Integer)
    outs_when_up = Column(Integer)
    inning = Column(Integer)
    inning_topbot = Column(String(10))
    
    # Hit coordinates
    hc_x = Column(Float)
    hc_y = Column(Float)
    
    # Deprecated timestamp fields
    tfs_deprecated = Column(String(100))
    tfs_zulu_deprecated = Column(String(100))
    
    # Officials and identifiers
    umpire = Column(Integer)
    sv_id = Column(String(100))  # This is the play ID for videos
    
    # Physics vectors
    vx0 = Column(Float)
    vy0 = Column(Float)
    vz0 = Column(Float)
    ax = Column(Float)
    ay = Column(Float)
    az = Column(Float)
    
    # Strike zone dimensions
    sz_top = Column(Float)
    sz_bot = Column(Float)
    
    # Hit outcome data
    hit_distance_sc = Column(Float)
    launch_speed = Column(Float)
    launch_angle = Column(Float)
    effective_speed = Column(Float)
    release_spin_rate = Column(Float)
    release_extension = Column(Float)
    game_pk = Column(Integer)
    
    # Defensive positions
    fielder_2 = Column(Integer)
    fielder_3 = Column(Integer)
    fielder_4 = Column(Integer)
    fielder_5 = Column(Integer)
    fielder_6 = Column(Integer)
    fielder_7 = Column(Integer)
    fielder_8 = Column(Integer)
    fielder_9 = Column(Integer)
    release_pos_y = Column(Float)
    
    # Expected outcome statistics
    estimated_ba_using_speedangle = Column(Float)
    estimated_woba_using_speedangle = Column(Float)
    woba_value = Column(Float)
    woba_denom = Column(Integer)
    babip_value = Column(Float)
    iso_value = Column(Float)
    launch_speed_angle = Column(Integer)
    
    # At-bat sequencing
    at_bat_number = Column(Integer)
    pitch_number = Column(Integer)
    pitch_name = Column(String(50))
    
    # Score state
    home_score = Column(Integer)
    away_score = Column(Integer)
    bat_score = Column(Integer)
    fld_score = Column(Integer)
    post_away_score = Column(Integer)
    post_home_score = Column(Integer)
    post_bat_score = Column(Integer)
    post_fld_score = Column(Integer)
    
    # Defensive alignment
    if_fielding_alignment = Column(String(20))
    of_fielding_alignment = Column(String(20))
    
    # Advanced pitch metrics
    spin_axis = Column(Float)
    delta_home_win_exp = Column(Float)
    delta_run_exp = Column(Float)
    
    # ⚔️ SWORD SWING METRICS - The critical fields for sword analysis ⚔️
    bat_speed = Column(Float)
    swing_length = Column(Float)
    
    # More expected stats
    estimated_slg_using_speedangle = Column(Float)
    delta_pitcher_run_exp = Column(Float)
    hyper_speed = Column(Float)
    home_score_diff = Column(Integer)
    bat_score_diff = Column(Integer)
    home_win_exp = Column(Float)
    bat_win_exp = Column(Float)
    
    # Player age data
    age_pit_legacy = Column(Float)
    age_bat_legacy = Column(Float)
    age_pit = Column(Float)
    age_bat = Column(Float)
    
    # Game context metrics
    n_thruorder_pitcher = Column(Integer)
    n_priorpa_thisgame_player_at_bat = Column(Integer)
    pitcher_days_since_prev_game = Column(Integer)
    batter_days_since_prev_game = Column(Integer)
    pitcher_days_until_next_game = Column(Integer)
    batter_days_until_next_game = Column(Integer)
    
    # Advanced break measurements
    api_break_z_with_gravity = Column(Float)
    api_break_x_arm = Column(Float)
    api_break_x_batter_in = Column(Float)
    arm_angle = Column(Float)
    
    # ⚔️ MORE CRITICAL SWORD SWING METRICS ⚔️
    attack_angle = Column(Float)
    attack_direction = Column(Float)
    swing_path_tilt = Column(Float)
    intercept_ball_minus_batter_pos_x_inches = Column(Float)
    intercept_ball_minus_batter_pos_y_inches = Column(Float)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to sword swing analysis
    sword_swing = relationship("SwordSwing", back_populates="pitch", uselist=False)

class SwordSwing(Base):
    """
    Sword swing analysis results with scores and expert commentary
    """
    __tablename__ = 'sword_swings'

    id = Column(Integer, primary_key=True)
    pitch_id = Column(Integer, ForeignKey('statcast_pitches.id'))
    
    # Sword scoring
    sword_score = Column(Float) # This is the universally scaled score (e.g., 50-100)
    raw_sword_metric = Column(Float) # The raw sum of weighted components, before 50-100 scaling
    is_sword_swing = Column(Boolean, default=True)
    
    # Analysis results
    percentile_analysis = Column(JSON)  # Store all percentile data
    percentile_highlights = Column(JSON)  # Array of highlight strings
    elite_metrics = Column(JSON)  # Array of elite metric names
    what_made_it_special = Column(Text)
    
    # Expert commentary
    expert_analysis = Column(Text)
    expert_analysis_generated_at = Column(DateTime)
    
    # Video links
    video_url = Column(String(500))
    download_url = Column(String(500))
    local_mp4_path = Column(String(500))  # Local file path for embedded video
    mp4_downloaded = Column(Boolean, default=False)
    mp4_file_size = Column(Integer)  # File size in bytes
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to pitch
    pitch = relationship("StatcastPitch", back_populates="sword_swing")

class DailyResults(Base):
    """
    Track which dates have been fully processed
    """
    __tablename__ = 'daily_results'

    id = Column(Integer, primary_key=True)
    date = Column(String(10), unique=True)  # YYYY-MM-DD
    total_pitches = Column(Integer)
    sword_swings_found = Column(Integer)
    processing_completed_at = Column(DateTime)
    expert_analysis_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

def create_tables():
    """Create all tables"""
    engine = create_engine(os.environ.get("DATABASE_URL"))
    Base.metadata.create_all(engine)

@contextmanager
def get_db():
    """Get database session"""
    engine = create_engine(os.environ.get("DATABASE_URL"))
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
