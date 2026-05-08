#!/usr/bin/env python3
"""
SwordFinder API - FastAPI backend for sword swing videos
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import httpx
import os
import re
from supabase import create_client
from dotenv import load_dotenv
from env_config import get_env
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
DEFAULT_UI_BASE_URL = "https://swordfinder.com"
DEFAULT_XAI_MODEL = "grok-4.3"
XAI_CHAT_COMPLETIONS_URL = "https://api.x.ai/v1/chat/completions"
X_POST_CHAR_LIMIT = 280


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


class ShareDraftRequest(BaseModel):
    date: str
    limit: int = DAILY_SLATE_MAX_LIMIT
    tone: Optional[str] = "sharp, funny, and baseball-native"


def normalize_sword_row(row: dict) -> dict:
    """Present legacy sword rows from the hitter perspective."""
    normalized = dict(row)
    source_player_name = row.get("player_name")
    batter_name = row.get("batter_name")
    pitcher_name = row.get("pitcher_name") or source_player_name

    if batter_name:
        normalized["source_player_name"] = source_player_name
        normalized["player_name"] = batter_name
    normalized["pitcher_name"] = pitcher_name

    return normalized


def normalize_sword_rows(rows: list) -> list:
    return [normalize_sword_row(row) for row in rows]


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


def format_display_date(date: str) -> str:
    dt = datetime.strptime(date, "%Y-%m-%d")
    return dt.strftime("%B %d, %Y").replace(" 0", " ")


def format_stat(value, decimals: int = 1, fallback: str = "--") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return f"{number:.{decimals}f}"


def build_x_post_page_url(date: str) -> str:
    base_url = (get_env("PUBLIC_UI_BASE_URL") or get_env("UI_BASE_URL") or DEFAULT_UI_BASE_URL).rstrip("/")
    return f"{base_url}/?date={date}"


def build_x_post_prompt(date: str, rows: list) -> str:
    normalized_rows = normalize_sword_rows(rows)
    display_date = format_display_date(date)
    page_url = build_x_post_page_url(date)
    lines = [
        f"Selected date: {display_date}",
        f"SwordFinder page: {page_url}",
        "Daily top swords:",
    ]

    for idx, row in enumerate(normalized_rows[:DAILY_SLATE_MAX_LIMIT], start=1):
        hitter = row.get("batter_name") or row.get("player_name") or "Unknown hitter"
        pitcher = row.get("pitcher_name") or "Unknown pitcher"
        pitch = row.get("pitch_name") or row.get("pitch_type") or "Pitch"
        release_speed = format_stat(row.get("release_speed"))
        score = format_stat(row.get("sword_score"))
        bat_speed = format_stat(row.get("bat_speed"))
        swing_length = format_stat(row.get("swing_length"))
        miss = format_stat(row.get("strike_zone_distance_inches"))
        description = row.get("description") or row.get("events") or "swinging strike"
        video_status = "video ready" if row.get("video_azure_blob_url") else "video pending"

        lines.append(
            f"{idx}. {hitter} vs {pitcher} (hitter: {hitter}; pitcher: {pitcher}): "
            f"pitcher threw {pitch} {release_speed} mph, "
            f"{description}, score {score}, bat {bat_speed} mph, "
            f"swing {swing_length} ft, miss {miss} in, {video_status}"
        )

    return "\n".join(lines)


def build_xai_chat_payload(
    request: ShareDraftRequest,
    rows: list,
    model: Optional[str] = None,
) -> dict:
    model_name = model or get_env("XAI_MODEL") or DEFAULT_XAI_MODEL
    tone = request.tone or "sharp, funny, and baseball-native"

    return {
        "model": model_name,
        "stream": False,
        "temperature": 0.7,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write tight, witty baseball posts for SwordFinder. "
                    "Return one X post under 260 characters. "
                    "Use only facts from the provided slate. "
                    "Do not invent scores, teams, injuries, stats, or video status. "
                    "Never describe the hitter as throwing the pitch; hitters swing against pitchers. "
                    "Do not write hitter possessives like 'Seager's changeup'; use pitcher possessives or 'against'. "
                    "No markdown, no quote marks, no thread numbering."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Tone: {tone}.\n"
                    "Draft one post for this daily SwordFinder slate:\n\n"
                    f"{build_x_post_prompt(request.date, rows)}"
                ),
            },
        ],
    }


def extract_xai_draft(response_payload: dict) -> str:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("xAI response did not include a chat completion message") from exc

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        content = " ".join(parts)

    if not isinstance(content, str) or not content.strip():
        raise ValueError("xAI response draft was empty")

    return content.strip().strip('"').strip("'").strip()


def trim_x_post_text(text: str, limit: int = X_POST_CHAR_LIMIT) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 3, 0)].rstrip() + "..."


async def request_xai_post_draft(request: ShareDraftRequest, rows: list) -> dict:
    api_key = get_env("XAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="XAI_API_KEY is not configured")

    payload = build_xai_chat_payload(request, rows)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(XAI_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
        response.raise_for_status()
        raw = response.json()
        draft = trim_x_post_text(extract_xai_draft(raw))
    except httpx.HTTPStatusError as exc:
        detail = f"xAI draft request failed with status {exc.response.status_code}"
        raise HTTPException(status_code=502, detail=detail) from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "date": request.date,
        "draft": draft,
        "character_count": len(draft),
        "limit": X_POST_CHAR_LIMIT,
        "model": payload["model"],
        "source": "xai",
        "page_url": build_x_post_page_url(request.date),
        "row_count": len(rows),
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
    query = query.gte('sword_score', MIN_PUBLIC_SWORD_SCORE)
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


@app.post("/share/x/draft")
async def draft_x_post(request: ShareDraftRequest):
    """Draft an editable X post for a daily top-five slate using server-side xAI."""
    validated_date = validate_slate_date(request.date)
    capped_limit = clamp_daily_slate_limit(request.limit)
    normalized_request = ShareDraftRequest(
        date=validated_date,
        limit=capped_limit,
        tone=request.tone,
    )

    try:
        rows = fetch_daily_slate_rows(validated_date, capped_limit)
        if not rows:
            raise HTTPException(status_code=404, detail="No swords found for this date")

        return await request_xai_post_draft(normalized_request, normalize_sword_rows(rows))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
            .gte('sword_score', MIN_PUBLIC_SWORD_SCORE)\
            .execute()
        
        # Total with videos
        videos_result = supabase.table('mlb_pitches_enhanced')\
            .select('id', count='exact')\
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
