"""FastAPI routes for SwordFinder X sharing workflows."""

from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from api_services.sword_rows import normalize_sword_row, normalize_sword_rows
from api_services import x_sharing as x

router = APIRouter(prefix="/share/x", tags=["share-x"])

_validate_slate_date: Optional[Callable[[str], str]] = None
_clamp_daily_slate_limit: Optional[Callable[[int], int]] = None
_fetch_daily_slate_rows: Optional[Callable[[str, int], list]] = None
_hydrate_missing_daily_slate_videos: Optional[Callable[[list, str], object]] = None


def configure_share_x_dependencies(
    *,
    validate_slate_date: Callable[[str], str],
    clamp_daily_slate_limit: Callable[[int], int],
    fetch_daily_slate_rows: Callable[[str, int], list],
    hydrate_missing_daily_slate_videos: Callable[[list, str], object],
) -> None:
    global _validate_slate_date
    global _clamp_daily_slate_limit
    global _fetch_daily_slate_rows
    global _hydrate_missing_daily_slate_videos

    _validate_slate_date = validate_slate_date
    _clamp_daily_slate_limit = clamp_daily_slate_limit
    _fetch_daily_slate_rows = fetch_daily_slate_rows
    _hydrate_missing_daily_slate_videos = hydrate_missing_daily_slate_videos


def _require_dependencies() -> None:
    if not all(
        [
            _validate_slate_date,
            _clamp_daily_slate_limit,
            _fetch_daily_slate_rows,
            _hydrate_missing_daily_slate_videos,
        ]
    ):
        raise RuntimeError("share-x route dependencies are not configured")


@router.post("/draft")
async def draft_x_post(http_request: Request, draft_request: x.ShareDraftRequest):
    """Draft an editable X post for a daily top-five slate."""
    _require_dependencies()
    x.require_x_sharing_enabled()

    validated_date = _validate_slate_date(draft_request.date)
    capped_limit = _clamp_daily_slate_limit(draft_request.limit)
    normalized_request = x.ShareDraftRequest(
        date=validated_date,
        limit=capped_limit,
        tone=draft_request.tone,
    )

    try:
        rows = _fetch_daily_slate_rows(validated_date, capped_limit)
        if not rows:
            raise HTTPException(status_code=404, detail="No swords found for this date")

        normalized_rows = normalize_sword_rows(rows)
        if x.request_has_x_admin_access(http_request):
            return await x.request_xai_post_draft(normalized_request, normalized_rows)
        return x.build_template_x_post_draft(normalized_request, normalized_rows)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/oauth/status")
async def x_oauth_status(request: Request):
    """Return whether the browser has an active X posting session."""
    if not x.x_sharing_enabled():
        return {
            "configured": False,
            "connected": False,
            "screen_name": None,
            "user_id": None,
            "disabled": True,
            "message": x.X_SHARING_DISABLED_DETAIL,
            "media_upload_enabled": False,
        }

    session = x.get_x_session(request)
    if session:
        return {
            "configured": x.x_oauth_is_configured() or x.x_oauth2_is_configured(),
            "connected": True,
            "screen_name": session.get("screen_name"),
            "user_id": session.get("user_id"),
            "disabled": False,
            "admin_required": False,
            "auth_mode": "oauth1_browser_session",
            "media_upload_enabled": x.x_media_upload_enabled(),
        }

    if x.x_oauth2_is_configured():
        if not x.request_has_x_admin_access(request):
            return {
                "configured": True,
                "connected": False,
                "screen_name": None,
                "user_id": None,
                "disabled": False,
                "admin_required": True,
                "message": x.X_ADMIN_REQUIRED_DETAIL,
                "auth_mode": "oauth2_user_token",
                "media_upload_enabled": False,
                "oauth2_scopes": [],
                "media_write_scope": False,
            }

        return {
            "configured": True,
            "connected": True,
            "screen_name": x.x_screen_name(),
            "user_id": x.get_env("X_USER_ID") or x.get_env("TWITTER_USER_ID"),
            "disabled": False,
            "admin_required": False,
            "auth_mode": "oauth2_user_token",
            "media_upload_enabled": x.x_media_upload_enabled(),
            "oauth2_scopes": sorted(x.x_oauth2_granted_scopes()),
            "media_write_scope": x.x_oauth2_has_scope("media.write"),
        }

    return {
        "configured": x.x_oauth_is_configured(),
        "connected": False,
        "screen_name": None,
        "user_id": None,
        "disabled": False,
        "media_upload_enabled": x.x_media_upload_enabled(),
    }


@router.get("/oauth/start")
async def x_oauth_start(request: Request, return_to: Optional[str] = None):
    """Start X 3-legged OAuth and redirect the user to X authorization."""
    x.require_x_sharing_enabled()

    safe_return_to = x.x_safe_return_to(return_to)
    callback_url = x.x_oauth_callback_url(request)

    token_payload = await x.request_x_oauth_token(callback_url)
    oauth_token = x.store_x_oauth_request(token_payload, return_to=safe_return_to)

    return RedirectResponse(x.x_oauth_authorize_url(oauth_token), status_code=302)


@router.get("/oauth/start-pin")
async def x_oauth_start_pin():
    """Start X PIN-based OAuth for apps without an approved web callback."""
    x.require_x_sharing_enabled()

    token_payload = await x.request_x_oauth_token("oob")
    oauth_token = x.store_x_oauth_request(token_payload)
    return {
        "mode": "pin",
        "authorize_url": x.x_oauth_authorize_url(oauth_token),
        "oauth_token": oauth_token,
        "expires_in": x.X_OAUTH_REQUEST_TTL_SECONDS,
    }


@router.get("/oauth/callback", name="x_oauth_callback")
async def x_oauth_callback(
    oauth_token: Optional[str] = None,
    oauth_verifier: Optional[str] = None,
    denied: Optional[str] = None,
):
    """Complete X OAuth, create a browser posting session, then return to the UI."""
    x.require_x_sharing_enabled()

    if denied:
        return RedirectResponse(f"{x.DEFAULT_UI_BASE_URL}/?x=denied", status_code=302)
    if not oauth_token or not oauth_verifier:
        raise HTTPException(status_code=400, detail="Missing OAuth callback parameters")

    request_state = x.X_OAUTH_REQUESTS.pop(oauth_token, None)
    if not request_state:
        raise HTTPException(status_code=400, detail="OAuth request token was not found or expired")

    access_payload = await x.exchange_x_access_token(
        oauth_token=oauth_token,
        oauth_verifier=oauth_verifier,
        request_token_secret=request_state["oauth_token_secret"],
    )
    session_id, _ = x.create_x_session(access_payload)

    response = RedirectResponse(request_state["return_to"], status_code=302)
    x.set_x_session_cookie(response, session_id)
    return response


@router.post("/oauth/pin")
async def x_oauth_pin(pin_request: x.XOAuthPinRequest, response: Response):
    """Complete X PIN-based OAuth and create a browser posting session."""
    x.require_x_sharing_enabled()

    oauth_token = (pin_request.oauth_token or "").strip()
    pin = (pin_request.pin or "").strip()
    if not oauth_token or not pin:
        raise HTTPException(status_code=400, detail="OAuth token and PIN are required")

    x.prune_x_oauth_requests()
    request_state = x.X_OAUTH_REQUESTS.pop(oauth_token, None)
    if not request_state:
        raise HTTPException(status_code=400, detail="OAuth request token was not found or expired")

    access_payload = await x.exchange_x_access_token(
        oauth_token=oauth_token,
        oauth_verifier=pin,
        request_token_secret=request_state["oauth_token_secret"],
    )
    session_id, session = x.create_x_session(access_payload)
    x.set_x_session_cookie(response, session_id)
    return {
        "connected": True,
        "screen_name": session.get("screen_name"),
        "user_id": session.get("user_id"),
    }


@router.post("/post")
async def post_to_x(request: Request, post: x.XPostRequest):
    """Publish an approved SwordFinder post through the connected X user session."""
    x.require_x_sharing_enabled()

    session = x.get_x_session(request)
    if session:
        result = await x.create_x_post(post.text, session)
        return {
            **result,
            "date": post.date,
            "screen_name": session.get("screen_name"),
            "auth_mode": "oauth1_browser_session",
        }

    if x.x_oauth2_is_configured():
        x.require_x_admin_access(request)
        access_token = await x.get_x_oauth2_user_token()
        try:
            result = await x.create_x_post_oauth2(post.text, access_token)
        except HTTPException as exc:
            if exc.status_code != 401 or not x.x_oauth2_refresh_token():
                raise
            access_token = await x.get_x_oauth2_user_token(force_refresh=True)
            result = await x.create_x_post_oauth2(post.text, access_token)
        return {
            **result,
            "date": post.date,
            "screen_name": x.x_screen_name(),
            "auth_mode": "oauth2_user_token",
        }

    raise HTTPException(status_code=401, detail="Connect X before posting")


@router.post("/top-sword")
async def post_top_sword_to_x(request: Request, post: x.TopSwordPostRequest):
    """Publish the selected day's #1 sword with native video and stats."""
    _require_dependencies()
    x.require_x_sharing_enabled()
    x.require_x_admin_access(request)

    validated_date = _validate_slate_date(post.date)
    rows = _fetch_daily_slate_rows(validated_date, 1)
    hydrated = 0

    if not rows:
        raise HTTPException(status_code=404, detail="No swords found for this date")

    top_row = normalize_sword_row(rows[0])
    if not top_row.get("video_azure_blob_url"):
        hydrated = await _hydrate_missing_daily_slate_videos([top_row], validated_date)
        if hydrated > 0:
            rows = _fetch_daily_slate_rows(validated_date, 1)
            top_row = normalize_sword_row(rows[0]) if rows else top_row

    if not top_row.get("video_azure_blob_url"):
        raise HTTPException(status_code=409, detail="Top sword video is not available yet")

    text = x.validate_x_post_text(post.text) if post.text else x.build_top_sword_post_text(validated_date, top_row)
    preview = {
        "date": validated_date,
        "dry_run": post.dry_run,
        "text": text,
        "video_url": top_row.get("video_azure_blob_url"),
        "hydrated": hydrated,
        "top_sword": top_row,
        "media_upload_enabled": x.x_media_upload_enabled(),
        "post_mode": "video" if x.x_media_upload_enabled() else "link",
    }
    if post.dry_run:
        return preview

    if not x.x_media_upload_enabled():
        result = await x.post_top_sword_link(text, request)
        return {
            **preview,
            **result,
            "screen_name": x.x_screen_name() or result.get("screen_name"),
        }

    session = x.get_x_session(request)
    result = await x.upload_and_post_top_sword_video(text, top_row["video_azure_blob_url"], session)
    return {
        **preview,
        **result,
        "screen_name": x.x_screen_name() or (session.get("screen_name") if session else None),
    }
