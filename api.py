#!/usr/bin/env python3
"""
SwordFinder API - FastAPI backend for sword swing videos
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import os
import re
from supabase import create_client
from dotenv import load_dotenv
from env_config import get_env
from api_services.sword_rows import normalize_sword_row, normalize_sword_rows
from api_services.x_sharing import (
    ShareDraftRequest,
    TopSwordPostRequest,
    XOAuthPinRequest,
    XPostRequest,
)
from starlette.concurrency import run_in_threadpool

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
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "https://swordfinder.com",
    "https://www.swordfinder.com",
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
VIDEO_BACKLOG_SELECT = (
    "id,game_date,batter_name,pitcher_name,player_name,pitch_type,pitch_name,"
    "description,events,bat_speed,swing_length,sword_score,"
    "strike_zone_distance_inches,video_azure_blob_url,video_processed_at"
)
DAILY_SLATE_MAX_LIMIT = 5
MIN_PUBLIC_SWORD_SCORE = 90.0
PROFILE_SWORD_MAX_LIMIT = 80
PROFILE_VIDEO_HYDRATION_MAX = 12
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# Pydantic models
class SwordSwing(BaseModel):
    id: Optional[int] = None
    player_name: Optional[str] = None
    source_player_name: Optional[str] = None
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


def clamp_daily_slate_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = DAILY_SLATE_MAX_LIMIT
    return max(1, min(parsed, DAILY_SLATE_MAX_LIMIT))


def clamp_profile_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = PROFILE_SWORD_MAX_LIMIT
    return max(1, min(parsed, PROFILE_SWORD_MAX_LIMIT))


def clamp_profile_hydration_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = PROFILE_VIDEO_HYDRATION_MAX
    return max(0, min(parsed, PROFILE_SWORD_MAX_LIMIT))


def profile_video_hydration_limit() -> int:
    return clamp_profile_hydration_limit(
        os.getenv("PROFILE_VIDEO_HYDRATION_MAX", PROFILE_VIDEO_HYDRATION_MAX)
    )


def validate_slate_date(date: str) -> str:
    if not date or not DATE_ONLY_RE.match(str(date)):
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD")

    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be a valid YYYY-MM-DD date")

    return date


def validate_profile_date_range(start_date: str, end_date: str) -> tuple:
    validated_start = validate_slate_date(start_date)
    validated_end = validate_slate_date(end_date)

    start_dt = datetime.strptime(validated_start, "%Y-%m-%d")
    end_dt = datetime.strptime(validated_end, "%Y-%m-%d")
    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")

    return validated_start, validated_end


def validate_entity_id(entity_id: int) -> int:
    try:
        parsed = int(entity_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Profile id must be a positive integer")

    if parsed <= 0:
        raise HTTPException(status_code=400, detail="Profile id must be a positive integer")

    return parsed


def normalize_profile_kind(profile_kind: str) -> str:
    normalized = str(profile_kind or "").strip().lower()
    if normalized == "player":
        return "batter"
    if normalized in {"pitcher", "batter"}:
        return normalized
    raise HTTPException(status_code=400, detail="profile_kind must be pitcher or batter")


def profile_filter_column(profile_kind: str) -> str:
    return normalize_profile_kind(profile_kind)


def find_missing_video_rows(rows: list) -> list:
    return [row for row in rows if not row.get("video_azure_blob_url")]


def build_profile_swords_response(
    profile_kind: str,
    entity_id: int,
    limit: int,
    rows: list,
    total_pitches: int,
    hydrated: int = 0,
) -> dict:
    normalized_rows = normalize_sword_rows(rows)

    return {
        "profile_kind": normalize_profile_kind(profile_kind),
        "entity_id": entity_id,
        "limit": limit,
        "count": len(normalized_rows),
        "total_pitches": total_pitches,
        "hydrated": hydrated,
        "pending_videos": len(find_missing_video_rows(normalized_rows)),
        "rows": normalized_rows,
        "last_checked": utc_now_iso(),
    }


def build_daily_slate_response(
    date: str,
    limit: int,
    rows: list,
    hydrated: int = 0,
) -> dict:
    normalized_rows = normalize_sword_rows(rows)

    return {
        "date": date,
        "limit": limit,
        "count": len(normalized_rows),
        "hydrated": hydrated,
        "pending_videos": len(find_missing_video_rows(normalized_rows)),
        "rows": normalized_rows,
        "last_checked": utc_now_iso(),
    }


def normalize_video_backlog_row(row: dict) -> dict:
    """Present pending video rows from the hitter perspective."""
    normalized = normalize_sword_row(row)
    normalized["video_status"] = (
        "cached" if normalized.get("video_azure_blob_url") else "pending"
    )
    return normalized


def normalize_video_backlog_rows(rows: list) -> list:
    return [normalize_video_backlog_row(row) for row in rows]


def build_video_backlog_status(
    date: Optional[str],
    total_swords: int,
    cached_videos: int,
    pending_rows: list,
) -> dict:
    pending_videos = max(total_swords - cached_videos, 0)
    cache_rate = round(cached_videos / total_swords, 4) if total_swords else 0.0

    return {
        "date": date,
        "total_swords": total_swords,
        "cached_videos": cached_videos,
        "pending_videos": pending_videos,
        "cache_rate": cache_rate,
        "top_pending": normalize_video_backlog_rows(pending_rows),
        "last_checked": utc_now_iso(),
    }


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


def _apply_video_backlog_base(query, date: Optional[str] = None):
    query = query.eq('game_type', 'R').gte('sword_score', MIN_PUBLIC_SWORD_SCORE)
    if date:
        query = query.eq('game_date', date)
    return query


def _count_video_backlog_rows(date: Optional[str] = None, cached: Optional[bool] = None) -> int:
    query = supabase.table('mlb_pitches_enhanced').select('id', count='exact')
    query = _apply_video_backlog_base(query, date)

    if cached is True:
        query = query.not_.is_('video_azure_blob_url', 'null')
    elif cached is False:
        query = query.is_('video_azure_blob_url', 'null')

    result = query.limit(1).execute()
    return result.count or 0


def fetch_daily_slate_rows(date: str, limit: int) -> list:
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq('game_date', date)\
        .eq('game_type', 'R')\
        .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
        .order('sword_score', desc=True)\
        .limit(limit)\
        .execute()

    return result.data or []


def fetch_profile_sword_rows(
    profile_kind: str,
    entity_id: int,
    start_date: str,
    end_date: str,
    limit: int,
) -> list:
    filter_column = profile_filter_column(profile_kind)
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq(filter_column, entity_id)\
        .eq('game_type', 'R')\
        .gte('game_date', start_date)\
        .lt('game_date', end_date)\
        .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
        .order('sword_score', desc=True)\
        .limit(limit)\
        .execute()

    return result.data or []


def fetch_profile_total_pitches(
    profile_kind: str,
    entity_id: int,
    start_date: str,
    end_date: str,
) -> int:
    filter_column = profile_filter_column(profile_kind)
    result = supabase.table('mlb_pitches_enhanced')\
        .select('id', count='exact')\
        .eq(filter_column, entity_id)\
        .gte('game_date', start_date)\
        .lt('game_date', end_date)\
        .limit(1)\
        .execute()

    return result.count or 0


async def hydrate_missing_daily_slate_videos(rows: list, date: str) -> int:
    missing_rows = find_missing_video_rows(rows)
    if not missing_rows:
        return 0

    import pandas as pd
    from process_daily_sword_videos import process_videos_for_swords

    return await run_in_threadpool(
        process_videos_for_swords,
        pd.DataFrame(missing_rows),
        date,
    )


async def hydrate_missing_profile_videos(rows: list) -> int:
    missing_rows = find_missing_video_rows(rows)
    hydration_limit = profile_video_hydration_limit()
    if not missing_rows or hydration_limit == 0:
        return 0

    target_rows = missing_rows[:hydration_limit]

    import pandas as pd
    from process_daily_sword_videos import process_videos_for_swords

    processed = 0
    rows_by_date = {}
    for row in target_rows:
        game_date = row.get("game_date")
        if not game_date:
            continue
        rows_by_date.setdefault(game_date, []).append(row)

    for game_date, dated_rows in rows_by_date.items():
        processed += await run_in_threadpool(
            process_videos_for_swords,
            pd.DataFrame(dated_rows),
            game_date,
        )

    return processed


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


@app.get("/daily-slate")
async def get_daily_slate(date: str, limit: int = 5, ensure_videos: bool = True):
    """Return a capped daily top-five slate, optionally caching missing clips first."""
    validated_date = validate_slate_date(date)
    capped_limit = clamp_daily_slate_limit(limit)
    hydrated = 0
    hydration_error = None

    try:
        rows = fetch_daily_slate_rows(validated_date, capped_limit)

        if ensure_videos:
            try:
                hydrated = await hydrate_missing_daily_slate_videos(rows, validated_date)
            except Exception as exc:
                hydration_error = str(exc)

            if hydrated > 0:
                rows = fetch_daily_slate_rows(validated_date, capped_limit)

        response = build_daily_slate_response(
            date=validated_date,
            limit=capped_limit,
            rows=rows,
            hydrated=hydrated,
        )
        if hydration_error:
            response["hydration_error"] = hydration_error
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/profiles/{profile_kind}/{entity_id}/swords")
async def get_profile_swords(
    profile_kind: str,
    entity_id: int,
    start_date: str,
    end_date: str,
    limit: int = PROFILE_SWORD_MAX_LIMIT,
    ensure_videos: bool = True,
):
    """Return a hitter or pitcher sword profile, optionally caching visible missing clips first."""
    normalized_kind = normalize_profile_kind(profile_kind)
    validated_entity_id = validate_entity_id(entity_id)
    validated_start, validated_end = validate_profile_date_range(start_date, end_date)
    capped_limit = clamp_profile_limit(limit)
    hydrated = 0
    hydration_error = None

    try:
        rows = fetch_profile_sword_rows(
            profile_kind=normalized_kind,
            entity_id=validated_entity_id,
            start_date=validated_start,
            end_date=validated_end,
            limit=capped_limit,
        )
        total_pitches = fetch_profile_total_pitches(
            profile_kind=normalized_kind,
            entity_id=validated_entity_id,
            start_date=validated_start,
            end_date=validated_end,
        )

        if ensure_videos:
            try:
                hydrated = await hydrate_missing_profile_videos(rows)
            except Exception as exc:
                hydration_error = str(exc)

            if hydrated > 0:
                rows = fetch_profile_sword_rows(
                    profile_kind=normalized_kind,
                    entity_id=validated_entity_id,
                    start_date=validated_start,
                    end_date=validated_end,
                    limit=capped_limit,
                )

        response = build_profile_swords_response(
            profile_kind=normalized_kind,
            entity_id=validated_entity_id,
            limit=capped_limit,
            rows=rows,
            total_pitches=total_pitches,
            hydrated=hydrated,
        )
        if hydration_error:
            response["hydration_error"] = hydration_error
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


from api_routes.share_x import (
    configure_share_x_dependencies,
    draft_x_post,
    post_to_x,
    post_top_sword_to_x,
    router as share_x_router,
    x_oauth_callback,
    x_oauth_pin,
    x_oauth_start,
    x_oauth_start_pin,
    x_oauth_status,
)

configure_share_x_dependencies(
    validate_slate_date=validate_slate_date,
    clamp_daily_slate_limit=clamp_daily_slate_limit,
    fetch_daily_slate_rows=lambda date, limit: fetch_daily_slate_rows(date, limit),
    hydrate_missing_daily_slate_videos=(
        lambda rows, date: hydrate_missing_daily_slate_videos(rows, date)
    ),
)
app.include_router(share_x_router)


@app.get("/ops/video-backlog")
async def get_video_backlog(date: Optional[str] = None, limit: int = 50):
    """List pending sword video cache rows."""
    limit = max(1, min(limit, 200))

    try:
        query = supabase.table('mlb_pitches_enhanced')\
            .select(VIDEO_BACKLOG_SELECT)
        query = _apply_video_backlog_base(query, date)
        result = query\
            .is_('video_azure_blob_url', 'null')\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()

        return {
            "date": date,
            "limit": limit,
            "count": len(result.data or []),
            "pending": normalize_video_backlog_rows(result.data or []),
            "last_checked": utc_now_iso(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/ops/video-backlog/status")
async def get_video_backlog_status(date: Optional[str] = None, limit: int = 10):
    """Summarize sword video cache coverage for all data or one date."""
    limit = max(1, min(limit, 100))

    try:
        total_swords = _count_video_backlog_rows(date=date)
        cached_videos = _count_video_backlog_rows(date=date, cached=True)

        pending_query = supabase.table('mlb_pitches_enhanced')\
            .select(VIDEO_BACKLOG_SELECT)
        pending_query = _apply_video_backlog_base(pending_query, date)
        pending_result = pending_query\
            .is_('video_azure_blob_url', 'null')\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()

        return build_video_backlog_status(
            date=date,
            total_swords=total_swords,
            cached_videos=cached_videos,
            pending_rows=pending_result.data or [],
        )
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
        "timestamp": utc_now_iso()
    }

@app.get("/swords/recent", response_model=List[SwordSwing])
async def get_recent_swords(limit: int = 10):
    """Get most recent sword swings with videos"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .eq('game_type', 'R')\
            .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
            .not_.is_('video_azure_blob_url', 'null')\
            .order('game_date', desc=True)\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()
        
        return normalize_sword_rows(result.data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/swords/top/{date}", response_model=List[SwordSwing])
async def get_top_swords_by_date(date: str, limit: int = 10):
    """Get top sword swings for a specific date"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .eq('game_date', date)\
            .eq('game_type', 'R')\
            .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()
        
        return normalize_sword_rows(result.data)
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
            .eq('batter_name', player_name)\
            .eq('game_type', 'R')\
            .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
            .order('sword_score', desc=True)\
            .limit(limit)\
            .execute()
        
        return normalize_sword_rows(result.data)
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
            .eq('game_type', 'R')\
            .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
            .execute()
        
        # Total with videos
        videos_result = supabase.table('mlb_pitches_enhanced')\
            .select('id', count='exact')\
            .eq('game_type', 'R')\
            .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
            .not_.is_('video_azure_blob_url', 'null')\
            .execute()
        
        return {
            "total_pitches": total_result.count,
            "total_swords": swords_result.count,
            "total_videos": videos_result.count,
            "last_updated": utc_now_iso()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search/players")
async def search_players(q: str, limit: int = 10):
    """Search for players by name"""
    try:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('batter_name')\
            .ilike('batter_name', f'%{q}%')\
            .eq('game_type', 'R')\
            .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
            .limit(1000)\
            .execute()
        
        # Get unique players
        players = list(set([r['batter_name'] for r in result.data if r.get('batter_name')]))
        players.sort()
        
        return players[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Run with: uvicorn api:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
