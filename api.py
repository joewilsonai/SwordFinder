#!/usr/bin/env python3
"""
SwordFinder API - FastAPI backend for sword swing videos
"""

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import asyncio
import base64
import hashlib
import hmac
import httpx
import os
import re
import secrets
import time
from urllib.parse import parse_qsl, quote, urlencode, urlparse
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
X_OAUTH_REQUEST_TOKEN_URL = "https://api.x.com/oauth/request_token"
X_OAUTH_AUTHORIZE_URL = "https://api.x.com/oauth/authorize"
X_OAUTH_ACCESS_TOKEN_URL = "https://api.x.com/oauth/access_token"
X_OAUTH2_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_CREATE_POST_URL = "https://api.x.com/2/tweets"
X_MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
X_MEDIA_UPLOAD_V2_BASE_URL = "https://api.x.com/2/media/upload"
X_MEDIA_UPLOAD_V2_INITIALIZE_URL = f"{X_MEDIA_UPLOAD_V2_BASE_URL}/initialize"
X_OAUTH_COOKIE_NAME = "sf_x_session"
X_OAUTH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30
X_OAUTH_REQUEST_TTL_SECONDS = 10 * 60
X_MEDIA_CHUNK_SIZE = 4 * 1024 * 1024
X_MEDIA_PROCESSING_MAX_WAIT_SECONDS = 60
X_VIDEO_MAX_BYTES = 512 * 1024 * 1024
X_SHARING_DISABLED_DETAIL = "X sharing requires an OAuth2 token with tweet.write and media.write."
X_OAUTH_REQUESTS = {}
X_OAUTH_SESSIONS = {}
X_OAUTH2_TOKEN_CACHE = {}


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


class XPostRequest(BaseModel):
    text: str
    date: Optional[str] = None


class XOAuthPinRequest(BaseModel):
    oauth_token: str
    pin: str


class TopSwordPostRequest(BaseModel):
    date: str
    text: Optional[str] = None
    dry_run: bool = False


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


def build_top_sword_watch_url(date: str) -> str:
    base_url = (get_env("PUBLIC_UI_BASE_URL") or get_env("UI_BASE_URL") or DEFAULT_UI_BASE_URL).rstrip("/")
    return f"{base_url}/api/watch/top-sword?date={date}&rank=1"


def build_top_sword_post_text(date: str, row: dict) -> str:
    """Build the default native-video X caption for the top sword of a day."""
    normalized = normalize_sword_row(row)
    hitter = normalized.get("batter_name") or normalized.get("player_name") or "Unknown hitter"
    pitcher = normalized.get("pitcher_name") or "Unknown pitcher"
    pitch = normalized.get("pitch_name") or normalized.get("pitch_type") or "Pitch"
    release_speed = format_stat(normalized.get("release_speed"))
    score = format_stat(normalized.get("sword_score"))
    bat_speed = format_stat(normalized.get("bat_speed"))
    swing_length = format_stat(normalized.get("swing_length"))
    miss = format_stat(normalized.get("strike_zone_distance_inches"))
    page_url = build_top_sword_watch_url(date)

    body = (
        f"Sword of the Day: {hitter} vs {pitcher}. "
        f"{pitch} {release_speed} mph. "
        f"Score {score} | bat {bat_speed} mph | swing {swing_length} ft | miss {miss} in."
    )
    return build_x_share_text(body, page_url)


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
                    "Do not imply the hitter succeeded, hit the ball well, or owned the pitch; a sword is a bad swing. "
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


def build_x_share_text(draft: str, page_url: str, limit: int = X_POST_CHAR_LIMIT) -> str:
    """Append the selected slate URL while keeping the X composer text in bounds."""
    cleaned_url = (page_url or "").strip()
    cleaned_draft = re.sub(r"\s+", " ", draft or "").strip()
    if not cleaned_url:
        return trim_x_post_text(cleaned_draft, limit)

    if cleaned_url in cleaned_draft:
        return trim_x_post_text(cleaned_draft, limit)

    separator = "\n\n"
    remaining = limit - len(separator) - len(cleaned_url)
    if remaining <= 0:
        return trim_x_post_text(cleaned_url, limit)

    return f"{trim_x_post_text(cleaned_draft, remaining)}{separator}{cleaned_url}"


def x_consumer_key() -> Optional[str]:
    return get_env("X_API_KEY") or get_env("TWITTER_API_KEY")


def x_consumer_secret() -> Optional[str]:
    return get_env("X_API_SECRET") or get_env("TWITTER_API_SECRET")


def x_oauth_is_configured() -> bool:
    return bool(x_consumer_key() and x_consumer_secret())


def get_secret_env(name: str, *fallback_names: str) -> Optional[str]:
    """Read an env secret, preferring NAME_B64 when hosts reject raw token-like values."""
    names = (name, *fallback_names)
    for candidate in names:
        encoded = get_env(f"{candidate}_B64")
        if not encoded:
            continue
        try:
            decoded = base64.b64decode(encoded.strip(), validate=True).decode().strip()
        except Exception:
            raise HTTPException(status_code=503, detail=f"{candidate}_B64 is not valid base64")
        return decoded or None

    for candidate in names:
        value = get_env(candidate)
        if value:
            return value
    return None


def x_oauth2_access_token() -> Optional[str]:
    return X_OAUTH2_TOKEN_CACHE.get("access_token") or get_secret_env("X_OAUTH2_ACCESS_TOKEN")


def x_oauth2_refresh_token() -> Optional[str]:
    return X_OAUTH2_TOKEN_CACHE.get("refresh_token") or get_secret_env("X_OAUTH2_REFRESH_TOKEN")


def parse_oauth2_scopes(value: Optional[str]) -> set:
    return {scope for scope in re.split(r"[\s,]+", value or "") if scope}


def x_oauth2_granted_scopes() -> set:
    return parse_oauth2_scopes(
        X_OAUTH2_TOKEN_CACHE.get("scope")
        or get_env("X_OAUTH2_SCOPE")
        or get_env("TWITTER_OAUTH2_SCOPE")
    )


def x_oauth2_has_scope(scope: str) -> bool:
    return scope in x_oauth2_granted_scopes()


def x_oauth2_client_id() -> Optional[str]:
    return get_secret_env("X_CLIENT_ID", "TWITTER_CLIENT_ID")


def x_oauth2_client_secret() -> Optional[str]:
    return get_secret_env("X_CLIENT_SECRET", "TWITTER_CLIENT_SECRET")


def x_screen_name() -> Optional[str]:
    return get_env("X_SCREEN_NAME") or get_env("TWITTER_SCREEN_NAME")


def x_oauth2_is_configured() -> bool:
    return bool(x_oauth2_access_token() or x_oauth2_refresh_token())


def x_sharing_enabled() -> bool:
    configured = (get_env("X_SHARING_ENABLED") or "").lower()
    if configured in {"0", "false", "no", "off"}:
        return False
    if configured in {"1", "true", "yes", "on"}:
        return True
    return x_oauth2_is_configured()


def x_media_upload_enabled() -> bool:
    configured = (get_env("X_MEDIA_UPLOAD_ENABLED") or "").lower()
    if configured in {"0", "false", "no", "off"}:
        return False

    scopes = x_oauth2_granted_scopes()
    if scopes:
        return "media.write" in scopes

    if x_oauth2_is_configured():
        return False

    return True


def x_oauth_callback_url(request: Request) -> str:
    configured = get_env("X_OAUTH_CALLBACK_URL") or get_env("TWITTER_OAUTH_CALLBACK_URL")
    if configured:
        return configured
    return str(request.url_for("x_oauth_callback"))


def x_safe_return_to(value: Optional[str]) -> str:
    default = (get_env("PUBLIC_UI_BASE_URL") or get_env("UI_BASE_URL") or DEFAULT_UI_BASE_URL).rstrip("/")
    if not value:
        return default

    parsed = urlparse(value)
    allowed_hosts = {
        "swordfinder.com",
        "www.swordfinder.com",
        "ui-one-henna.vercel.app",
        "localhost",
        "127.0.0.1",
    }
    if parsed.scheme in {"http", "https"} and parsed.hostname in allowed_hosts:
        return value
    return default


def oauth_percent_encode(value) -> str:
    return quote(str(value), safe="~")


def parse_oauth_form_response(body: str) -> dict:
    return dict(parse_qsl(body, keep_blank_values=True))


def x_oauth_authorize_url(oauth_token: str) -> str:
    return f"{X_OAUTH_AUTHORIZE_URL}?{urlencode({'oauth_token': oauth_token})}"


def prune_x_oauth_requests(now: Optional[float] = None) -> None:
    cutoff = (now or time.time()) - X_OAUTH_REQUEST_TTL_SECONDS
    expired = [
        token
        for token, state in X_OAUTH_REQUESTS.items()
        if state.get("created_at", 0) < cutoff
    ]
    for token in expired:
        X_OAUTH_REQUESTS.pop(token, None)


def store_x_oauth_request(token_payload: dict, return_to: Optional[str] = None) -> str:
    prune_x_oauth_requests()
    oauth_token = token_payload["oauth_token"]
    X_OAUTH_REQUESTS[oauth_token] = {
        "oauth_token_secret": token_payload["oauth_token_secret"],
        "return_to": return_to,
        "created_at": time.time(),
    }
    return oauth_token


def create_x_session(access_payload: dict) -> tuple:
    session_id = secrets.token_urlsafe(32)
    session = {
        "oauth_token": access_payload["oauth_token"],
        "oauth_token_secret": access_payload["oauth_token_secret"],
        "screen_name": access_payload.get("screen_name"),
        "user_id": access_payload.get("user_id"),
        "created_at": time.time(),
    }
    X_OAUTH_SESSIONS[session_id] = session
    return session_id, session


def set_x_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        X_OAUTH_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=X_OAUTH_COOKIE_MAX_AGE,
    )


def build_oauth1_authorization_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: Optional[str] = None,
    token_secret: str = "",
    extra_oauth_params: Optional[dict] = None,
    request_params: Optional[dict] = None,
) -> str:
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_urlsafe(24),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
    }
    if token:
        oauth_params["oauth_token"] = token
    if extra_oauth_params:
        oauth_params.update({key: value for key, value in extra_oauth_params.items() if value is not None})

    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    signature_params = {}
    signature_params.update(dict(parse_qsl(parsed.query, keep_blank_values=True)))
    if request_params:
        signature_params.update(request_params)
    signature_params.update(oauth_params)

    parameter_string = "&".join(
        f"{oauth_percent_encode(key)}={oauth_percent_encode(value)}"
        for key, value in sorted(signature_params.items())
    )
    signature_base = "&".join(
        [
            method.upper(),
            oauth_percent_encode(base_url),
            oauth_percent_encode(parameter_string),
        ]
    )
    signing_key = f"{oauth_percent_encode(consumer_secret)}&{oauth_percent_encode(token_secret)}"
    digest = hmac.new(signing_key.encode(), signature_base.encode(), hashlib.sha1).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode()

    return "OAuth " + ", ".join(
        f'{oauth_percent_encode(key)}="{oauth_percent_encode(value)}"'
        for key, value in sorted(oauth_params.items())
    )


async def request_x_oauth_token(callback_url: str) -> dict:
    consumer_key = x_consumer_key()
    consumer_secret = x_consumer_secret()
    if not consumer_key or not consumer_secret:
        raise HTTPException(status_code=503, detail="X OAuth API key/secret are not configured")

    extra = {"oauth_callback": callback_url}
    auth_header = build_oauth1_authorization_header(
        "POST",
        X_OAUTH_REQUEST_TOKEN_URL,
        consumer_key,
        consumer_secret,
        extra_oauth_params=extra,
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(X_OAUTH_REQUEST_TOKEN_URL, headers={"Authorization": auth_header})

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"X request-token failed with status {response.status_code}: {response.text[:200]}",
        )

    payload = parse_oauth_form_response(response.text)
    if payload.get("oauth_callback_confirmed") != "true":
        raise HTTPException(status_code=502, detail="X did not confirm the OAuth callback")
    if not payload.get("oauth_token") or not payload.get("oauth_token_secret"):
        raise HTTPException(status_code=502, detail="X request-token response was missing token fields")
    return payload


async def exchange_x_access_token(oauth_token: str, oauth_verifier: str, request_token_secret: str) -> dict:
    consumer_key = x_consumer_key()
    consumer_secret = x_consumer_secret()
    if not consumer_key or not consumer_secret:
        raise HTTPException(status_code=503, detail="X OAuth API key/secret are not configured")

    request_params = {"oauth_verifier": oauth_verifier}
    auth_header = build_oauth1_authorization_header(
        "POST",
        X_OAUTH_ACCESS_TOKEN_URL,
        consumer_key,
        consumer_secret,
        token=oauth_token,
        token_secret=request_token_secret,
        request_params=request_params,
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            X_OAUTH_ACCESS_TOKEN_URL,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=request_params,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"X access-token failed with status {response.status_code}: {response.text[:200]}",
        )

    payload = parse_oauth_form_response(response.text)
    if not payload.get("oauth_token") or not payload.get("oauth_token_secret"):
        raise HTTPException(status_code=502, detail="X access-token response was missing token fields")
    return payload


def get_x_session(request: Request) -> Optional[dict]:
    session_id = request.cookies.get(X_OAUTH_COOKIE_NAME)
    if not session_id:
        return None
    return X_OAUTH_SESSIONS.get(session_id)


def validate_x_post_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Post text is required")
    if len(cleaned) > X_POST_CHAR_LIMIT:
        raise HTTPException(status_code=400, detail=f"Post text must be {X_POST_CHAR_LIMIT} characters or fewer")
    return cleaned


def require_x_sharing_enabled() -> None:
    if not x_sharing_enabled():
        raise HTTPException(status_code=503, detail=X_SHARING_DISABLED_DETAIL)


def build_x_post_body(text: str, media_id: Optional[str] = None) -> dict:
    body = {"text": validate_x_post_text(text)}
    if media_id:
        body["media"] = {"media_ids": [str(media_id)]}
    return body


def x_api_error_status_code(response) -> int:
    status_code = getattr(response, "status_code", 502)
    if 400 <= status_code < 500:
        return status_code
    return 502


def x_api_error_detail(action: str, response) -> str:
    status_code = getattr(response, "status_code", "unknown")
    body = re.sub(r"\s+", " ", (getattr(response, "text", "") or "").strip())
    body_detail = body[:240] if body else "X returned an empty response"
    detail = f"{action} failed with status {status_code}: {body_detail}"

    if status_code == 403 and "media" in action.lower():
        detail += (
            ". X accepted the connected user session but denied media upload access. "
            "Native video posting requires X media upload access, such as an OAuth 2.0 "
            "user token with media.write or an app tier that can use the media upload endpoint."
        )
    return detail


def raise_x_api_error(action: str, response) -> None:
    raise HTTPException(
        status_code=x_api_error_status_code(response),
        detail=x_api_error_detail(action, response),
    )


def x_media_init_param_options(total_bytes: int, media_type: str) -> list:
    base_params = {
        "command": "INIT",
        "total_bytes": str(total_bytes),
        "media_type": media_type or "video/mp4",
    }
    return [
        {**base_params, "media_category": "tweet_video"},
        base_params,
    ]


def x_user_auth_header(
    method: str,
    url: str,
    session: dict,
    request_params: Optional[dict] = None,
) -> str:
    consumer_key = x_consumer_key()
    consumer_secret = x_consumer_secret()
    if not consumer_key or not consumer_secret:
        raise HTTPException(status_code=503, detail="X OAuth API key/secret are not configured")

    return build_oauth1_authorization_header(
        method,
        url,
        consumer_key,
        consumer_secret,
        token=session["oauth_token"],
        token_secret=session["oauth_token_secret"],
        request_params=request_params,
    )


async def download_video_bytes(video_url: str) -> tuple:
    if not video_url:
        raise HTTPException(status_code=409, detail="Top sword video is not available yet")

    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
        response = await client.get(video_url)

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Could not download video clip: {response.status_code}")
    if len(response.content) > X_VIDEO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Video clip is too large for X upload")

    media_type = response.headers.get("content-type", "").split(";")[0] or "video/mp4"
    return response.content, media_type


async def upload_x_video_bytes(video_bytes: bytes, media_type: str, session: dict) -> dict:
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Video clip was empty")

    async with httpx.AsyncClient(timeout=90.0) as client:
        init_response = None
        for init_index, init_params in enumerate(x_media_init_param_options(len(video_bytes), media_type)):
            init_response = await client.post(
                X_MEDIA_UPLOAD_URL,
                headers={
                    "Authorization": x_user_auth_header(
                        "POST",
                        X_MEDIA_UPLOAD_URL,
                        session,
                        request_params=init_params,
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=init_params,
            )
            if init_response.status_code < 400:
                break
            should_retry_without_category = init_response.status_code == 403 and init_index == 0
            if not should_retry_without_category:
                raise_x_api_error("X media INIT", init_response)

        init_payload = init_response.json()
        media_id = init_payload.get("media_id_string") or str(init_payload.get("media_id") or "")
        if not media_id:
            raise HTTPException(status_code=502, detail="X media INIT response did not include a media id")

        for segment_index, start in enumerate(range(0, len(video_bytes), X_MEDIA_CHUNK_SIZE)):
            chunk = video_bytes[start:start + X_MEDIA_CHUNK_SIZE]
            append_params = {
                "command": "APPEND",
                "media_id": media_id,
                "segment_index": str(segment_index),
            }
            append_url = f"{X_MEDIA_UPLOAD_URL}?{urlencode(append_params)}"
            append_response = await client.post(
                append_url,
                headers={"Authorization": x_user_auth_header("POST", append_url, session)},
                files={"media": ("swordfinder.mp4", chunk, media_type or "video/mp4")},
            )
            if append_response.status_code >= 400:
                raise_x_api_error("X media APPEND", append_response)

        finalize_params = {"command": "FINALIZE", "media_id": media_id}
        finalize_response = await client.post(
            X_MEDIA_UPLOAD_URL,
            headers={
                "Authorization": x_user_auth_header(
                    "POST",
                    X_MEDIA_UPLOAD_URL,
                    session,
                    request_params=finalize_params,
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=finalize_params,
        )
        if finalize_response.status_code >= 400:
            raise_x_api_error("X media FINALIZE", finalize_response)

        payload = finalize_response.json()
        processing = payload.get("processing_info")
        waited = 0
        while processing and processing.get("state") in {"pending", "in_progress"}:
            wait_seconds = max(1, min(int(processing.get("check_after_secs") or 2), 5))
            if waited + wait_seconds > X_MEDIA_PROCESSING_MAX_WAIT_SECONDS:
                raise HTTPException(status_code=504, detail="Timed out waiting for X video processing")
            await asyncio.sleep(wait_seconds)
            waited += wait_seconds

            status_params = {"command": "STATUS", "media_id": media_id}
            status_url = f"{X_MEDIA_UPLOAD_URL}?{urlencode(status_params)}"
            status_response = await client.get(
                status_url,
                headers={"Authorization": x_user_auth_header("GET", status_url, session)},
            )
            if status_response.status_code >= 400:
                raise_x_api_error("X media STATUS", status_response)
            payload = status_response.json()
            processing = payload.get("processing_info")

        if processing and processing.get("state") == "failed":
            error = processing.get("error", {}).get("message") or "X video processing failed"
            raise HTTPException(status_code=502, detail=error)

    return {"media_id": media_id, "media_type": media_type or "video/mp4"}


def x_oauth2_auth_headers(access_token: str, content_type: Optional[str] = None) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


async def refresh_x_oauth2_access_token() -> str:
    refresh_token = x_oauth2_refresh_token()
    client_id = x_oauth2_client_id()
    if not refresh_token or not client_id:
        raise HTTPException(status_code=503, detail=X_SHARING_DISABLED_DETAIL)

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    client_secret = x_oauth2_client_secret()
    if client_secret:
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {credentials}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(X_OAUTH2_TOKEN_URL, headers=headers, data=data)

    if response.status_code >= 400:
        raise_x_api_error("X OAuth2 refresh", response)

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="X OAuth2 refresh response did not include an access token")

    X_OAUTH2_TOKEN_CACHE["access_token"] = access_token
    if payload.get("refresh_token"):
        X_OAUTH2_TOKEN_CACHE["refresh_token"] = payload["refresh_token"]
    if payload.get("scope"):
        X_OAUTH2_TOKEN_CACHE["scope"] = payload["scope"]
    return access_token


async def get_x_oauth2_user_token(force_refresh: bool = False) -> str:
    if not force_refresh:
        access_token = x_oauth2_access_token()
        if access_token:
            return access_token
    return await refresh_x_oauth2_access_token()


async def upload_x_video_bytes_oauth2(video_bytes: bytes, media_type: str, access_token: str) -> dict:
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Video clip was empty")

    media_type = media_type or "video/mp4"
    async with httpx.AsyncClient(timeout=90.0) as client:
        init_response = await client.post(
            X_MEDIA_UPLOAD_V2_INITIALIZE_URL,
            headers=x_oauth2_auth_headers(access_token, "application/json"),
            json={
                "media_category": "tweet_video",
                "media_type": media_type,
                "shared": False,
                "total_bytes": len(video_bytes),
            },
        )
        if init_response.status_code >= 400:
            raise_x_api_error("X media INIT", init_response)

        init_payload = init_response.json().get("data", {})
        media_id = str(init_payload.get("id") or "")
        if not media_id:
            raise HTTPException(status_code=502, detail="X media INIT response did not include a media id")

        for segment_index, start in enumerate(range(0, len(video_bytes), X_MEDIA_CHUNK_SIZE)):
            chunk = video_bytes[start:start + X_MEDIA_CHUNK_SIZE]
            append_response = await client.post(
                f"{X_MEDIA_UPLOAD_V2_BASE_URL}/{media_id}/append",
                headers=x_oauth2_auth_headers(access_token),
                data={"segment_index": str(segment_index)},
                files={"media": ("swordfinder.mp4", chunk, media_type)},
            )
            if append_response.status_code >= 400:
                raise_x_api_error("X media APPEND", append_response)

        finalize_response = await client.post(
            f"{X_MEDIA_UPLOAD_V2_BASE_URL}/{media_id}/finalize",
            headers=x_oauth2_auth_headers(access_token),
        )
        if finalize_response.status_code >= 400:
            raise_x_api_error("X media FINALIZE", finalize_response)

        payload = finalize_response.json()
        processing = payload.get("data", {}).get("processing_info")
        waited = 0
        while processing and processing.get("state") in {"pending", "in_progress"}:
            wait_seconds = max(1, min(int(processing.get("check_after_secs") or 2), 5))
            if waited + wait_seconds > X_MEDIA_PROCESSING_MAX_WAIT_SECONDS:
                raise HTTPException(status_code=504, detail="Timed out waiting for X video processing")
            await asyncio.sleep(wait_seconds)
            waited += wait_seconds

            status_response = await client.get(
                X_MEDIA_UPLOAD_V2_BASE_URL,
                headers=x_oauth2_auth_headers(access_token),
                params={"media_id": media_id},
            )
            if status_response.status_code >= 400:
                raise_x_api_error("X media STATUS", status_response)
            payload = status_response.json()
            processing = payload.get("data", {}).get("processing_info")

        if processing and processing.get("state") == "failed":
            error = processing.get("error", {}).get("message") or "X video processing failed"
            raise HTTPException(status_code=502, detail=error)

    return {"media_id": media_id, "media_type": media_type}


async def create_x_post(text: str, session: dict, media_id: Optional[str] = None) -> dict:
    body = build_x_post_body(text, media_id=media_id)
    auth_header = x_user_auth_header("POST", X_CREATE_POST_URL, session)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            X_CREATE_POST_URL,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json=body,
        )

    if response.status_code >= 400:
        raise_x_api_error("X post", response)
    payload = response.json()
    post_id = payload.get("data", {}).get("id")
    if not post_id:
        raise HTTPException(status_code=502, detail="X post response did not include a post id")
    return {
        "posted": True,
        "id": post_id,
        "text": payload.get("data", {}).get("text", body["text"]),
        "url": f"https://x.com/{session.get('screen_name') or 'i'}/status/{post_id}",
        "media_id": media_id,
    }


async def create_x_post_oauth2(text: str, access_token: str, media_id: Optional[str] = None) -> dict:
    body = build_x_post_body(text, media_id=media_id)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            X_CREATE_POST_URL,
            headers=x_oauth2_auth_headers(access_token, "application/json"),
            json=body,
        )

    if response.status_code >= 400:
        raise_x_api_error("X post", response)
    payload = response.json()
    post_id = payload.get("data", {}).get("id")
    if not post_id:
        raise HTTPException(status_code=502, detail="X post response did not include a post id")
    screen_name = x_screen_name() or "i"
    return {
        "posted": True,
        "id": post_id,
        "text": payload.get("data", {}).get("text", body["text"]),
        "url": f"https://x.com/{screen_name}/status/{post_id}",
        "media_id": media_id,
    }


async def upload_and_post_top_sword_video(text: str, video_url: str, session: Optional[dict] = None) -> dict:
    video_bytes, media_type = await download_video_bytes(video_url)
    if x_oauth2_is_configured():
        access_token = await get_x_oauth2_user_token()
        try:
            media = await upload_x_video_bytes_oauth2(video_bytes, media_type, access_token)
            result = await create_x_post_oauth2(text, access_token, media_id=media["media_id"])
        except HTTPException as exc:
            if exc.status_code != 401 or not x_oauth2_refresh_token():
                raise
            access_token = await get_x_oauth2_user_token(force_refresh=True)
            media = await upload_x_video_bytes_oauth2(video_bytes, media_type, access_token)
            result = await create_x_post_oauth2(text, access_token, media_id=media["media_id"])
        return {**result, "media": media, "auth_mode": "oauth2_user_token"}

    if not session:
        raise HTTPException(status_code=401, detail="Connect X before posting")
    media = await upload_x_video_bytes(video_bytes, media_type, session)
    result = await create_x_post(text, session, media_id=media["media_id"])
    return {**result, "media": media}


async def post_top_sword_link(text: str, request: Request) -> dict:
    """Post the #1 sword text with a SwordFinder watch link when native media is unavailable."""
    if x_oauth2_is_configured():
        access_token = await get_x_oauth2_user_token()
        try:
            result = await create_x_post_oauth2(text, access_token)
        except HTTPException as exc:
            if exc.status_code != 401 or not x_oauth2_refresh_token():
                raise
            access_token = await get_x_oauth2_user_token(force_refresh=True)
            result = await create_x_post_oauth2(text, access_token)
        return {**result, "auth_mode": "oauth2_user_token", "post_mode": "link"}

    session = get_x_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Connect X before posting")
    result = await create_x_post(text, session)
    return {**result, "post_mode": "link"}


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

    page_url = build_x_post_page_url(request.date)
    share_text = build_x_share_text(draft, page_url)

    return {
        "date": request.date,
        "draft": draft,
        "share_text": share_text,
        "character_count": len(draft),
        "share_character_count": len(share_text),
        "limit": X_POST_CHAR_LIMIT,
        "model": payload["model"],
        "source": "xai",
        "page_url": page_url,
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


@app.post("/share/x/draft")
async def draft_x_post(request: ShareDraftRequest):
    """Draft an editable X post for a daily top-five slate using server-side xAI."""
    require_x_sharing_enabled()

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


@app.get("/share/x/oauth/status")
async def x_oauth_status(request: Request):
    """Return whether the browser has an active X posting session."""
    if x_oauth2_is_configured():
        return {
            "configured": True,
            "connected": True,
            "screen_name": x_screen_name(),
            "user_id": get_env("X_USER_ID") or get_env("TWITTER_USER_ID"),
            "disabled": False,
            "auth_mode": "oauth2_user_token",
            "media_upload_enabled": x_media_upload_enabled(),
            "oauth2_scopes": sorted(x_oauth2_granted_scopes()),
            "media_write_scope": x_oauth2_has_scope("media.write"),
        }

    if not x_sharing_enabled():
        return {
            "configured": False,
            "connected": False,
            "screen_name": None,
            "user_id": None,
            "disabled": True,
            "message": X_SHARING_DISABLED_DETAIL,
            "media_upload_enabled": False,
        }

    session = get_x_session(request)
    return {
        "configured": x_oauth_is_configured(),
        "connected": bool(session),
        "screen_name": session.get("screen_name") if session else None,
        "user_id": session.get("user_id") if session else None,
        "disabled": False,
        "media_upload_enabled": x_media_upload_enabled(),
    }


@app.get("/share/x/oauth/start")
async def x_oauth_start(request: Request, return_to: Optional[str] = None):
    """Start X 3-legged OAuth and redirect the user to X authorization."""
    require_x_sharing_enabled()

    safe_return_to = x_safe_return_to(return_to)
    callback_url = x_oauth_callback_url(request)

    token_payload = await request_x_oauth_token(callback_url)
    oauth_token = store_x_oauth_request(token_payload, return_to=safe_return_to)

    return RedirectResponse(x_oauth_authorize_url(oauth_token), status_code=302)


@app.get("/share/x/oauth/start-pin")
async def x_oauth_start_pin():
    """Start X PIN-based OAuth for apps without an approved web callback."""
    require_x_sharing_enabled()

    token_payload = await request_x_oauth_token("oob")
    oauth_token = store_x_oauth_request(token_payload)
    return {
        "mode": "pin",
        "authorize_url": x_oauth_authorize_url(oauth_token),
        "oauth_token": oauth_token,
        "expires_in": X_OAUTH_REQUEST_TTL_SECONDS,
    }


@app.get("/share/x/oauth/callback", name="x_oauth_callback")
async def x_oauth_callback(
    oauth_token: Optional[str] = None,
    oauth_verifier: Optional[str] = None,
    denied: Optional[str] = None,
):
    """Complete X OAuth, create a browser posting session, then return to the UI."""
    require_x_sharing_enabled()

    if denied:
        return RedirectResponse(f"{DEFAULT_UI_BASE_URL}/?x=denied", status_code=302)
    if not oauth_token or not oauth_verifier:
        raise HTTPException(status_code=400, detail="Missing OAuth callback parameters")

    request_state = X_OAUTH_REQUESTS.pop(oauth_token, None)
    if not request_state:
        raise HTTPException(status_code=400, detail="OAuth request token was not found or expired")

    access_payload = await exchange_x_access_token(
        oauth_token=oauth_token,
        oauth_verifier=oauth_verifier,
        request_token_secret=request_state["oauth_token_secret"],
    )
    session_id, _ = create_x_session(access_payload)

    response = RedirectResponse(request_state["return_to"], status_code=302)
    set_x_session_cookie(response, session_id)
    return response


@app.post("/share/x/oauth/pin")
async def x_oauth_pin(pin_request: XOAuthPinRequest, response: Response):
    """Complete X PIN-based OAuth and create a browser posting session."""
    require_x_sharing_enabled()

    oauth_token = (pin_request.oauth_token or "").strip()
    pin = (pin_request.pin or "").strip()
    if not oauth_token or not pin:
        raise HTTPException(status_code=400, detail="OAuth token and PIN are required")

    prune_x_oauth_requests()
    request_state = X_OAUTH_REQUESTS.pop(oauth_token, None)
    if not request_state:
        raise HTTPException(status_code=400, detail="OAuth request token was not found or expired")

    access_payload = await exchange_x_access_token(
        oauth_token=oauth_token,
        oauth_verifier=pin,
        request_token_secret=request_state["oauth_token_secret"],
    )
    session_id, session = create_x_session(access_payload)
    set_x_session_cookie(response, session_id)
    return {
        "connected": True,
        "screen_name": session.get("screen_name"),
        "user_id": session.get("user_id"),
    }


@app.post("/share/x/post")
async def post_to_x(request: Request, post: XPostRequest):
    """Publish an approved SwordFinder post through the connected X user session."""
    require_x_sharing_enabled()

    if x_oauth2_is_configured():
        access_token = await get_x_oauth2_user_token()
        try:
            result = await create_x_post_oauth2(post.text, access_token)
        except HTTPException as exc:
            if exc.status_code != 401 or not x_oauth2_refresh_token():
                raise
            access_token = await get_x_oauth2_user_token(force_refresh=True)
            result = await create_x_post_oauth2(post.text, access_token)
        return {
            **result,
            "date": post.date,
            "screen_name": x_screen_name(),
            "auth_mode": "oauth2_user_token",
        }

    session = get_x_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Connect X before posting")

    result = await create_x_post(post.text, session)
    return {
        **result,
        "date": post.date,
        "screen_name": session.get("screen_name"),
    }


@app.post("/share/x/top-sword")
async def post_top_sword_to_x(request: Request, post: TopSwordPostRequest):
    """Publish the selected day's #1 sword with native video and stats."""
    require_x_sharing_enabled()

    validated_date = validate_slate_date(post.date)
    rows = fetch_daily_slate_rows(validated_date, 1)
    hydrated = 0

    if not rows:
        raise HTTPException(status_code=404, detail="No swords found for this date")

    top_row = normalize_sword_row(rows[0])
    if not top_row.get("video_azure_blob_url"):
        hydrated = await hydrate_missing_daily_slate_videos([top_row], validated_date)
        if hydrated > 0:
            rows = fetch_daily_slate_rows(validated_date, 1)
            top_row = normalize_sword_row(rows[0]) if rows else top_row

    if not top_row.get("video_azure_blob_url"):
        raise HTTPException(status_code=409, detail="Top sword video is not available yet")

    text = validate_x_post_text(post.text) if post.text else build_top_sword_post_text(validated_date, top_row)
    preview = {
        "date": validated_date,
        "dry_run": post.dry_run,
        "text": text,
        "video_url": top_row.get("video_azure_blob_url"),
        "hydrated": hydrated,
        "top_sword": top_row,
        "media_upload_enabled": x_media_upload_enabled(),
        "post_mode": "video" if x_media_upload_enabled() else "link",
    }
    if post.dry_run:
        return preview

    if not x_media_upload_enabled():
        result = await post_top_sword_link(text, request)
        return {
            **preview,
            **result,
            "screen_name": x_screen_name() or result.get("screen_name"),
        }

    session = get_x_session(request)
    result = await upload_and_post_top_sword_video(text, top_row["video_azure_blob_url"], session)
    return {
        **preview,
        **result,
        "screen_name": x_screen_name() or (session.get("screen_name") if session else None),
    }


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
