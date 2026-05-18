"""X/Twitter sharing and xAI draft helpers for SwordFinder."""

import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse

import httpx
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from env_config import get_env
from api_services.sword_rows import normalize_sword_row, normalize_sword_rows

DAILY_SLATE_MAX_LIMIT = 5
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
X_ADMIN_REQUIRED_DETAIL = "X sharing endpoints require a SwordFinder admin token."
X_OAUTH_REQUESTS = {}
X_OAUTH_SESSIONS = {}
X_OAUTH2_TOKEN_CACHE = {}


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


def x_oauth1_access_token() -> Optional[str]:
    return get_secret_env("X_ACCESS_TOKEN", "TWITTER_ACCESS_TOKEN")


def x_oauth1_access_token_secret() -> Optional[str]:
    return get_secret_env("X_ACCESS_TOKEN_SECRET", "TWITTER_ACCESS_TOKEN_SECRET")


def x_oauth1_user_token_is_configured() -> bool:
    return bool(
        x_consumer_key()
        and x_consumer_secret()
        and x_oauth1_access_token()
        and x_oauth1_access_token_secret()
    )


def x_oauth1_env_session() -> Optional[dict]:
    if not x_oauth1_user_token_is_configured():
        return None
    return {
        "oauth_token": x_oauth1_access_token(),
        "oauth_token_secret": x_oauth1_access_token_secret(),
        "screen_name": x_screen_name(),
        "user_id": get_env("X_USER_ID") or get_env("TWITTER_USER_ID"),
        "created_at": time.time(),
    }


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


def x_admin_token() -> Optional[str]:
    return get_secret_env("SWORDFINDER_ADMIN_TOKEN", "X_POST_ADMIN_TOKEN")


def request_header_value(request: Request, header_name: str) -> Optional[str]:
    headers = getattr(request, "headers", {}) or {}
    if hasattr(headers, "get"):
        value = headers.get(header_name) or headers.get(header_name.lower())
        if value is not None:
            return value

    items = getattr(headers, "items", lambda: [])()
    for key, value in items:
        if str(key).lower() == header_name.lower():
            return value
    return None


def request_admin_token(request: Request) -> Optional[str]:
    authorization = (request_header_value(request, "Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None

    for header_name in ("X-SwordFinder-Admin-Token", "X-Admin-Token"):
        token = (request_header_value(request, header_name) or "").strip()
        if token:
            return token
    return None


def request_has_x_admin_access(request: Request) -> bool:
    configured_token = x_admin_token()
    provided_token = request_admin_token(request)
    return bool(
        configured_token
        and provided_token
        and secrets.compare_digest(provided_token, configured_token)
    )


def require_x_admin_access(request: Request) -> None:
    if not x_admin_token():
        raise HTTPException(
            status_code=503,
            detail=f"{X_ADMIN_REQUIRED_DETAIL} Set SWORDFINDER_ADMIN_TOKEN.",
        )

    if not request_has_x_admin_access(request):
        raise HTTPException(status_code=403, detail=X_ADMIN_REQUIRED_DETAIL)


def x_media_upload_enabled() -> bool:
    configured = (get_env("X_MEDIA_UPLOAD_ENABLED") or "").lower()
    if configured in {"0", "false", "no", "off"}:
        return False

    if x_oauth1_user_token_is_configured():
        return True

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

    oauth1_session = x_oauth1_env_session() or session
    if oauth1_session:
        media = await upload_x_video_bytes(video_bytes, media_type, oauth1_session)
        result = await create_x_post(text, oauth1_session, media_id=media["media_id"])
        auth_mode = "oauth1_user_token" if x_oauth1_env_session() else "oauth1_browser_session"
        return {**result, "media": media, "auth_mode": auth_mode}

    if x_oauth2_is_configured() and x_oauth2_has_scope("media.write"):
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

    raise HTTPException(status_code=503, detail=X_SHARING_DISABLED_DETAIL)


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


def build_template_x_post_draft(request: ShareDraftRequest, rows: list) -> dict:
    normalized_rows = normalize_sword_rows(rows)
    top_row = normalized_rows[0] if normalized_rows else {}
    hitter = top_row.get("batter_name") or top_row.get("player_name") or "Unknown hitter"
    pitcher = top_row.get("pitcher_name") or "Unknown pitcher"
    pitch = top_row.get("pitch_name") or top_row.get("pitch_type") or "pitch"
    score = format_stat(top_row.get("sword_score"))
    draft = trim_x_post_text(
        f"Today's SwordFinder leader: {hitter} vs {pitcher}. "
        f"{pitch}, sword score {score}. The daily top-five slate is live."
    )
    page_url = build_x_post_page_url(request.date)
    share_text = build_x_share_text(draft, page_url)

    return {
        "date": request.date,
        "draft": draft,
        "share_text": share_text,
        "character_count": len(draft),
        "share_character_count": len(share_text),
        "limit": X_POST_CHAR_LIMIT,
        "model": None,
        "source": "template",
        "page_url": page_url,
        "row_count": len(rows),
    }
