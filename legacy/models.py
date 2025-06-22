from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class StatcastPitch(Base):
    """
    Complete Statcast pitch data - stores everything from the CSV
    """
    __tablename__ = 'statcast_pitches'
    
    id = Column(Integer, primary_key=True)
    
    # Game info
    game_pk = Column(Integer)
    game_date = Column(String(10))  # YYYY-MM-DD
    home_team = Column(String(10))
    away_team = Column(String(10))
    inning = Column(Integer)
    
    # At-bat info
    at_bat_number = Column(Integer)
    pitch_number = Column(Integer)
    balls = Column(Integer)
    strikes = Column(Integer)
    
    # Player info
    batter = Column(Integer)
    pitcher = Column(Integer)
    batter_name = Column(String(100))
    pitcher_name = Column(String(100))
    
    # Pitch data
    pitch_type = Column(String(10))
    pitch_name = Column(String(50))
    release_speed = Column(Float)
    release_spin_rate = Column(Float)
    release_extension = Column(Float)
    
    # Location
    plate_x = Column(Float)
    plate_z = Column(Float)
    sz_top = Column(Float)
    sz_bot = Column(Float)
    
    # Movement
    pfx_x = Column(Float)
    pfx_z = Column(Float)
    effective_speed = Column(Float)
    
    # Swing data (if available)
    bat_speed = Column(Float)
    swing_path_tilt = Column(Float)
    attack_angle = Column(Float)
    intercept_ball_minus_batter_pos_y_inches = Column(Float)
    
    # Outcome
    description = Column(String(100))
    events = Column(String(100))
    
    # Video
    play_id = Column(String(100))
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sword_swing = relationship("SwordSwing", back_populates="pitch", uselist=False)

class SwordSwing(Base):
    """
    Sword swing analysis results with scores and expert commentary
    """
    __tablename__ = 'sword_swings'
    
    id = Column(Integer, primary_key=True)
    pitch_id = Column(Integer, ForeignKey('statcast_pitches.id'))
    
    # Sword scoring
    sword_score = Column(Float)
    is_sword_swing = Column(Boolean, default=True)
    
    # Analysis results
    percentile_analysis = Column(JSON)  # Store all percentile data
    percentile_highlights = Column(JSON)  # Array of highlight strings
    elite_metrics = Column(JSON)  # Array of elite metric names
    what_made_it_special = Column(Text)
    
    # Expert AI analysis
    expert_analysis = Column(Text)
    expert_analysis_generated_at = Column(DateTime)
    
    # Video URLs and local storage
    video_url = Column(String(500))
    download_url = Column(String(500))
    local_mp4_path = Column(String(500))  # Local file path for embedded video
    mp4_downloaded = Column(Boolean, default=False)
    mp4_file_size = Column(Integer)  # File size in bytes
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
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

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()