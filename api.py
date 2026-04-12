#!/usr/bin/env python3
"""
SwordFinder API - FastAPI backend for sword swing videos
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
from supabase import create_client
from dotenv import load_dotenv
from env_config import get_env

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="SwordFinder API",
    description="API for the worst swings in baseball",
    version="1.0.0"
)

# CORS configuration (supports local dev + deployed UI; override via CORS_ORIGINS)
default_cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://ui-one-henna.vercel.app",
]

cors_origins_raw = os.getenv("CORS_ORIGINS", ",".join(default_cors_origins))
cors_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
allow_credentials = "*" not in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client (prefer service role for server-side reads)
supabase_url = get_env("SUPABASE_URL")
supabase_key = get_env("SUPABASE_SERVICE_ROLE_KEY") or get_env("SUPABASE_ANON_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Missing SUPABASE_URL and/or API key in environment")

supabase = create_client(supabase_url, supabase_key)
ALLOWED_TABLES = {"mlb_pitches_enhanced"}
RESERVED_QUERY_KEYS = {"table", "select", "order", "limit", "offset"}

# Pydantic models
class SwordSwing(BaseModel):
    id: Optional[int] = None
    player_name: Optional[str] = None
    pitcher_name: Optional[str] = None
    game_date: Optional[str] = None
    bat_speed: Optional[float] = None
    sword_score: Optional[float] = None
    pitch_type: Optional[str] = None
    release_speed: Optional[float] = None
    video_azure_blob_url: Optional[str]
    perceived_velocity: Optional[float]
    strike_zone_distance_inches: Optional[float]
    description: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    database: str
    project: str
    timestamp: str


def _apply_filter(query, column: str, expression: str):
    parts = expression.split(".")
    op = parts[0]
    rhs = ".".join(parts[1:]) if len(parts) > 1 else ""

    if op == "eq":
        return query.eq(column, rhs)
    if op == "gt":
        return query.gt(column, rhs)
    if op == "gte":
        return query.gte(column, rhs)
    if op == "lt":
        return query.lt(column, rhs)
    if op == "lte":
        return query.lte(column, rhs)
    if op == "ilike":
        return query.ilike(column, rhs)
    if op == "is":
        return query.is_(column, rhs)
    if op == "not" and len(parts) >= 3 and parts[1] == "is":
        return query.not_.is_(column, ".".join(parts[2:]))

    raise ValueError(f"Unsupported filter expression: {column}={expression}")


def _apply_order(query, order_expr: str):
    for clause in order_expr.split(","):
        clause = clause.strip()
        if not clause:
            continue
        col, _, direction = clause.partition(".")
        query = query.order(col, desc=direction.lower() == "desc")
    return query


def _validate_table(table: str):
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"Table not allowed: {table}")


@app.get("/data/rows")
async def get_rows(
    request: Request,
    table: str = "mlb_pitches_enhanced",
    select: str = "*",
    order: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Read-only query endpoint used by static UI pages."""
    _validate_table(table)
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)

    try:
        query = supabase.table(table).select(select)

        for key, value in request.query_params.multi_items():
            if key in RESERVED_QUERY_KEYS:
                continue
            query = _apply_filter(query, key, value)

        if order:
            query = _apply_order(query, order)

        query = query.range(offset, offset + limit - 1)
        result = query.execute()
        return result.data
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/data/count")
async def get_count(
    request: Request,
    table: str = "mlb_pitches_enhanced",
    select: str = "id",
):
    """Count rows using the same filter syntax as /data/rows."""
    _validate_table(table)

    try:
        query = supabase.table(table).select(select, count="exact")

        for key, value in request.query_params.multi_items():
            if key in RESERVED_QUERY_KEYS:
                continue
            query = _apply_filter(query, key, value)

        result = query.limit(1).execute()
        return {"count": result.count or 0}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

# Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API and database health"""
    try:
        # If this query executes without raising, the connection is healthy.
        supabase.table('mlb_pitches_enhanced').select('id').limit(1).execute()
        db_status = "connected"
    except Exception:
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
