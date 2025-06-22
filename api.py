#!/usr/bin/env python3
"""
SwordFinder API - FastAPI backend for sword swing videos
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="SwordFinder API",
    description="API for the worst swings in baseball",
    version="1.0.0"
)

# CORS configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React/Vite defaults
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_ANON_KEY')  # Use anon key for API

if not supabase_url or not supabase_key:
    raise ValueError("Missing Supabase credentials in environment")

supabase = create_client(supabase_url, supabase_key)

# Pydantic models
class SwordSwing(BaseModel):
    id: int
    player_name: str
    pitcher_name: str
    game_date: str
    bat_speed: float
    sword_score: float
    pitch_type: str
    release_speed: float
    video_azure_blob_url: Optional[str]
    perceived_velocity: Optional[float]
    strike_zone_distance_inches: Optional[float]
    description: str

class HealthResponse(BaseModel):
    status: str
    database: str
    project: str
    timestamp: str

# Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API and database health"""
    try:
        # Test database connection
        result = supabase.table('mlb_pitches_enhanced').select('id').limit(1).execute()
        db_status = "connected" if result.data else "error"
    except:
        db_status = "error"
    
    return {
        "status": "healthy",
        "database": db_status,
        "project": "Swordfinder (seagurfpitfslyxxxztw)",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/swords/recent", response_model=List[SwordSwing])
async def get_recent_swords(limit: int = 10):
    """Get most recent sword swings with videos"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .gt('sword_score', 80)\
            .not_.is_('video_azure_blob_url', 'null')\
            .order('game_date', desc=True)\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()
        
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/swords/top/{date}", response_model=List[SwordSwing])
async def get_top_swords_by_date(date: str, limit: int = 10):
    """Get top sword swings for a specific date"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .eq('game_date', date)\
            .gt('sword_score', 0)\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()
        
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/swords/worst", response_model=List[SwordSwing])
async def get_worst_swords(limit: int = 20):
    """Get the absolute worst sword swings of all time"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .gt('sword_score', 100)\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()
        
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/players/{player_name}/swords", response_model=List[SwordSwing])
async def get_player_swords(player_name: str, limit: int = 50):
    """Get all sword swings for a specific player"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .eq('player_name', player_name)\
            .gt('sword_score', 0)\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()
        
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats/overview")
async def get_stats_overview():
    """Get overview statistics"""
    try:
        # Total pitches
        total_result = supabase.table('mlb_pitches_enhanced')\
            .select('id', count='exact')\
            .execute()
        
        # Total swords
        swords_result = supabase.table('mlb_pitches_enhanced')\
            .select('id', count='exact')\
            .gt('sword_score', 0)\
            .execute()
        
        # Total with videos
        videos_result = supabase.table('mlb_pitches_enhanced')\
            .select('id', count='exact')\
            .not_.is_('video_azure_blob_url', 'null')\
            .execute()
        
        return {
            "total_pitches": total_result.count,
            "total_swords": swords_result.count,
            "total_videos": videos_result.count,
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search/players")
async def search_players(q: str, limit: int = 10):
    """Search for players by name"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('player_name')\
            .ilike('player_name', f'%{q}%')\
            .gt('sword_score', 0)\
            .limit(1000)\
            .execute()
        
        # Get unique players
        players = list(set([r['player_name'] for r in result.data]))
        players.sort()
        
        return players[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Run with: uvicorn api:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 