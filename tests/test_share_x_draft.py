import asyncio
import base64
import pytest
from fastapi import HTTPException

import api
from api_services import x_sharing as x_api
from api_services.x_sharing import (
    ShareDraftRequest,
    TopSwordPostRequest,
    XPostRequest,
    build_oauth1_authorization_header,
    build_top_sword_post_text,
    build_x_share_text,
    build_x_post_body,
    build_x_post_page_url,
    build_x_post_prompt,
    x_api_error_detail,
    x_api_error_status_code,
    build_xai_chat_payload,
    create_x_session,
    extract_xai_draft,
    parse_oauth_form_response,
    prune_x_oauth_requests,
    store_x_oauth_request,
    trim_x_post_text,
    validate_x_post_text,
    x_oauth_authorize_url,
    x_oauth2_granted_scopes,
    x_safe_return_to,
    X_OAUTH_REQUESTS,
    X_OAUTH_SESSIONS,
    X_OAUTH_COOKIE_NAME,
)


SAMPLE_ROWS = [
    {
        "batter_name": "Corey Seager",
        "pitcher_name": "De Los Santos, Yerry",
        "pitch_name": "Changeup",
        "release_speed": 88.9,
        "description": "swinging_strike_blocked",
        "sword_score": 105.253,
        "bat_speed": 32.0,
        "swing_length": 6.0,
        "strike_zone_distance_inches": 11.8,
        "video_azure_blob_url": "https://example.test/seager.mp4",
    },
    {
        "batter_name": "Mickey Moniak",
        "pitcher_name": "Raley, Brooks",
        "pitch_name": "Sweeper",
        "release_speed": 78.7,
        "description": "swinging_strike",
        "sword_score": 101.4,
        "bat_speed": 34.1,
        "swing_length": 7.9,
        "strike_zone_distance_inches": 28.2,
        "video_azure_blob_url": None,
    },
]


def test_build_x_post_page_url_points_to_selected_date():
    assert (
        build_x_post_page_url("2026-05-06")
        == "https://swordfinder.com/?date=2026-05-06"
    )


def test_build_x_post_prompt_includes_ranked_slate_context():
    prompt = build_x_post_prompt("2026-05-06", SAMPLE_ROWS)

    assert "May 6, 2026" in prompt
    assert "1. Corey Seager vs De Los Santos, Yerry" in prompt
    assert "hitter: Corey Seager" in prompt
    assert "pitcher threw Changeup" in prompt
    assert "score 105.3" in prompt
    assert "miss 11.8 in" in prompt
    assert "video ready" in prompt
    assert "2. Mickey Moniak vs Raley, Brooks" in prompt
    assert "video pending" in prompt


def test_build_xai_chat_payload_uses_server_side_model_name():
    payload = build_xai_chat_payload(
        ShareDraftRequest(date="2026-05-06"),
        SAMPLE_ROWS,
        model="grok-test",
    )

    assert payload["model"] == "grok-test"
    assert payload["stream"] is False
    assert payload["temperature"] == 0.7
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert "under 260 characters" in payload["messages"][0]["content"]
    assert "Never describe the hitter as throwing the pitch" in payload["messages"][0]["content"]
    assert "Do not write hitter possessives like" in payload["messages"][0]["content"]
    assert "Do not imply the hitter succeeded" in payload["messages"][0]["content"]
    assert "Corey Seager" in payload["messages"][1]["content"]


def test_extract_xai_draft_reads_chat_completion_shape():
    response = {
        "choices": [
            {
                "message": {
                    "content": "The daily sword crown goes to Corey Seager. Brutal miss, beautiful clip."
                }
            }
        ]
    }

    assert extract_xai_draft(response).startswith("The daily sword crown")


def test_trim_x_post_text_keeps_drafts_inside_x_limit():
    draft = "x" * 400

    trimmed = trim_x_post_text(draft, limit=280)

    assert len(trimmed) == 280
    assert trimmed.endswith("...")


def test_build_x_share_text_appends_selected_slate_url_inside_limit():
    text = build_x_share_text(
        "Corey Seager took the daily sword crown with a 105.3.",
        "https://swordfinder.com/?date=2026-05-06",
    )

    assert "Corey Seager" in text
    assert "https://swordfinder.com/?date=2026-05-06" in text
    assert len(text) <= 280


def test_build_top_sword_post_text_includes_video_stats_and_page_url():
    text = build_top_sword_post_text("2026-05-06", SAMPLE_ROWS[0])

    assert "Sword of the Day" in text
    assert "Corey Seager vs De Los Santos, Yerry" in text
    assert "Changeup 88.9 mph" in text
    assert "Score 105.3" in text
    assert "bat 32.0 mph" in text
    assert "swing 6.0 ft" in text
    assert "miss 11.8 in" in text
    assert "https://swordfinder.com/api/watch/top-sword?date=2026-05-06&rank=1" in text
    assert len(text) <= 280


def test_build_x_post_body_attaches_media_id_when_present():
    assert build_x_post_body("hello") == {"text": "hello"}
    assert build_x_post_body("hello", media_id="12345") == {
        "text": "hello",
        "media": {"media_ids": ["12345"]},
    }


def test_x_api_error_detail_explains_empty_media_forbidden_response():
    class Response:
        status_code = 403
        text = ""

    detail = x_api_error_detail("X media INIT", Response())

    assert "X media INIT failed with status 403" in detail
    assert "empty response" in detail
    assert "media upload access" in detail
    assert "media.write" in detail


def test_x_api_error_status_code_preserves_client_auth_errors():
    class ForbiddenResponse:
        status_code = 403

    class ServerResponse:
        status_code = 503

    assert x_api_error_status_code(ForbiddenResponse()) == 403
    assert x_api_error_status_code(ServerResponse()) == 502


def test_x_oauth_status_reports_disabled_without_oauth2_token(monkeypatch):
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: default)

    class Request:
        cookies = {}

    status = asyncio.run(api.x_oauth_status(Request()))

    assert status["configured"] is False
    assert status["connected"] is False
    assert status["disabled"] is True
    assert "OAuth2 token" in status["message"]


def test_x_oauth_status_reports_oauth2_token_ready(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "X_OAUTH2_SCOPE": "tweet.read tweet.write users.read media.write offline.access",
        "X_SCREEN_NAME": "joewilsonai",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    class Request:
        cookies = {}
        headers = {"Authorization": "Bearer admin-token"}

    status = asyncio.run(api.x_oauth_status(Request()))

    assert status["configured"] is True
    assert status["connected"] is True
    assert status["disabled"] is False
    assert status["screen_name"] == "joewilsonai"
    assert status["auth_mode"] == "oauth2_user_token"
    assert status["media_upload_enabled"] is True
    assert status["media_write_scope"] is True
    assert "media.write" in status["oauth2_scopes"]


def test_x_oauth_status_hides_server_token_without_admin(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "X_SCREEN_NAME": "joewilsonai",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    class Request:
        cookies = {}
        headers = {}

    status = asyncio.run(api.x_oauth_status(Request()))

    assert status["configured"] is True
    assert status["connected"] is False
    assert status["screen_name"] is None
    assert status["admin_required"] is True
    assert status["media_upload_enabled"] is False


def test_x_oauth_status_prefers_browser_session_over_server_token(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
        "X_MEDIA_UPLOAD_ENABLED": "false",
    }
    session_id, _ = create_x_session(
        {
            "oauth_token": "browser-token",
            "oauth_token_secret": "browser-secret",
            "screen_name": "browser_user",
            "user_id": "123",
        }
    )
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    class Request:
        cookies = {X_OAUTH_COOKIE_NAME: session_id}
        headers = {}

    status = asyncio.run(api.x_oauth_status(Request()))

    assert status["connected"] is True
    assert status["screen_name"] == "browser_user"
    assert status["auth_mode"] == "oauth1_browser_session"
    X_OAUTH_SESSIONS.clear()


def test_x_oauth_status_reports_media_upload_disabled(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "X_SCREEN_NAME": "joewilsonai",
        "X_MEDIA_UPLOAD_ENABLED": "false",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    class Request:
        cookies = {}
        headers = {"X-SwordFinder-Admin-Token": "admin-token"}

    status = asyncio.run(api.x_oauth_status(Request()))

    assert status["connected"] is True
    assert status["media_upload_enabled"] is False


def test_x_admin_access_accepts_bearer_or_admin_header(monkeypatch):
    env = {"SWORDFINDER_ADMIN_TOKEN": "admin-token"}
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    class BearerRequest:
        headers = {"Authorization": "Bearer admin-token"}

    class HeaderRequest:
        headers = {"X-SwordFinder-Admin-Token": "admin-token"}

    assert x_api.request_has_x_admin_access(BearerRequest()) is True
    assert x_api.request_has_x_admin_access(HeaderRequest()) is True


def test_oauth2_env_prefers_base64_wrapped_values(monkeypatch):
    env = {
        "X_CLIENT_ID": "stale-client-id",
        "X_CLIENT_ID_B64": base64.b64encode(b"real-client-id").decode(),
        "X_CLIENT_SECRET_B64": base64.b64encode(b"real-client-secret").decode(),
        "X_OAUTH2_ACCESS_TOKEN_B64": base64.b64encode(b"real-access-token").decode(),
        "X_OAUTH2_REFRESH_TOKEN_B64": base64.b64encode(b"real-refresh-token").decode(),
    }
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    assert x_api.x_oauth2_client_id() == "real-client-id"
    assert x_api.x_oauth2_client_secret() == "real-client-secret"
    assert x_api.x_oauth2_access_token() == "real-access-token"
    assert x_api.x_oauth2_refresh_token() == "real-refresh-token"


def test_oauth2_scope_parser_reads_cache_or_env(monkeypatch):
    env = {"X_OAUTH2_SCOPE": "tweet.read tweet.write users.read media.write offline.access"}
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))
    x_api.X_OAUTH2_TOKEN_CACHE.clear()

    assert x_oauth2_granted_scopes() == {
        "tweet.read",
        "tweet.write",
        "users.read",
        "media.write",
        "offline.access",
    }

    x_api.X_OAUTH2_TOKEN_CACHE["scope"] = "tweet.read tweet.write"
    assert x_oauth2_granted_scopes() == {"tweet.read", "tweet.write"}
    x_api.X_OAUTH2_TOKEN_CACHE.clear()


def test_media_upload_requires_recorded_media_write_scope(monkeypatch):
    env = {"X_MEDIA_UPLOAD_ENABLED": "true", "X_OAUTH2_SCOPE": "tweet.read tweet.write users.read"}
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    assert x_api.x_media_upload_enabled() is False

    env["X_OAUTH2_SCOPE"] = "tweet.read tweet.write users.read media.write offline.access"
    assert x_api.x_media_upload_enabled() is True


def test_media_upload_allows_server_side_oauth1_user_token(monkeypatch):
    env = {
        "X_MEDIA_UPLOAD_ENABLED": "true",
        "X_OAUTH2_ACCESS_TOKEN": "oauth2-token",
        "X_OAUTH2_SCOPE": "tweet.read tweet.write users.read offline.access",
        "X_API_KEY": "consumer-key",
        "X_API_SECRET": "consumer-secret",
        "X_ACCESS_TOKEN": "oauth1-access",
        "X_ACCESS_TOKEN_SECRET": "oauth1-secret",
    }
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    assert x_api.x_oauth1_user_token_is_configured() is True
    assert x_api.x_media_upload_enabled() is True


def test_upload_and_post_top_sword_video_prefers_server_oauth1_for_media(monkeypatch):
    env_session = {
        "oauth_token": "oauth1-access",
        "oauth_token_secret": "oauth1-secret",
        "screen_name": "joewilsonai",
        "user_id": "1602704058594328576",
    }
    calls = []

    async def fake_download_video_bytes(video_url):
        calls.append(("download", video_url))
        return b"video-bytes", "video/mp4"

    async def fake_upload_x_video_bytes(video_bytes, media_type, session):
        calls.append(("oauth1_upload", video_bytes, media_type, session["oauth_token"]))
        return {"media_id": "media-123", "media_type": media_type}

    async def fake_create_x_post(text, session, media_id=None):
        calls.append(("oauth1_post", text, session["oauth_token"], media_id))
        return {"posted": True, "id": "post-123", "media_id": media_id}

    monkeypatch.setattr(x_api, "download_video_bytes", fake_download_video_bytes)
    monkeypatch.setattr(x_api, "x_oauth1_env_session", lambda: env_session)
    monkeypatch.setattr(x_api, "upload_x_video_bytes", fake_upload_x_video_bytes)
    monkeypatch.setattr(x_api, "create_x_post", fake_create_x_post)
    monkeypatch.setattr(x_api, "upload_x_video_bytes_oauth2", lambda *args, **kwargs: pytest.fail("oauth2 upload should not run"))

    result = asyncio.run(x_api.upload_and_post_top_sword_video("caption", "https://example.test/sword.mp4"))

    assert result["posted"] is True
    assert result["media_id"] == "media-123"
    assert result["auth_mode"] == "oauth1_user_token"
    assert calls == [
        ("download", "https://example.test/sword.mp4"),
        ("oauth1_upload", b"video-bytes", "video/mp4", "oauth1-access"),
        ("oauth1_post", "caption", "oauth1-access", "media-123"),
    ]


def test_oauth2_refresh_caches_granted_scope(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "scope": "tweet.read tweet.write media.write offline.access users.read",
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, data=None):
            return Response()

    env = {
        "X_CLIENT_ID": "client-id",
        "X_CLIENT_SECRET": "client-secret",
        "X_OAUTH2_REFRESH_TOKEN": "refresh-token",
    }
    x_api.X_OAUTH2_TOKEN_CACHE.clear()
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))
    monkeypatch.setattr(x_api.httpx, "AsyncClient", Client)

    access_token = asyncio.run(x_api.refresh_x_oauth2_access_token())

    assert access_token == "new-access"
    assert x_api.X_OAUTH2_TOKEN_CACHE["scope"] == "tweet.read tweet.write media.write offline.access users.read"
    x_api.X_OAUTH2_TOKEN_CACHE.clear()


def test_x_draft_endpoint_is_disabled_without_oauth2_token(monkeypatch):
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: default)

    class Request:
        headers = {}

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.draft_x_post(Request(), ShareDraftRequest(date="2026-05-06")))

    assert exc.value.status_code == 503
    assert "OAuth2 token" in exc.value.detail


def test_x_draft_endpoint_uses_template_without_admin_token(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }
    async def fail_xai(*args, **kwargs):
        pytest.fail("xAI should not be called without an admin token")

    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))
    monkeypatch.setattr(api, "fetch_daily_slate_rows", lambda date, limit: SAMPLE_ROWS)
    monkeypatch.setattr(x_api, "request_xai_post_draft", fail_xai)

    class Request:
        headers = {}

    result = asyncio.run(api.draft_x_post(Request(), ShareDraftRequest(date="2026-05-06")))

    assert result["source"] == "template"
    assert result["model"] is None
    assert "Corey Seager" in result["draft"]
    assert "https://swordfinder.com/?date=2026-05-06" in result["share_text"]


def test_x_draft_endpoint_uses_xai_with_admin_token(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }

    async def fake_xai(draft_request, rows):
        return {"source": "xai", "date": draft_request.date, "row_count": len(rows)}

    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))
    monkeypatch.setattr(api, "fetch_daily_slate_rows", lambda date, limit: SAMPLE_ROWS)
    monkeypatch.setattr(x_api, "request_xai_post_draft", fake_xai)

    class Request:
        headers = {"Authorization": "Bearer admin-token"}

    result = asyncio.run(api.draft_x_post(Request(), ShareDraftRequest(date="2026-05-06")))

    assert result == {"source": "xai", "date": "2026-05-06", "row_count": 2}


def test_post_to_x_requires_admin_for_server_token(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }
    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    class Request:
        cookies = {}
        headers = {}

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.post_to_x(Request(), XPostRequest(text="draft")))

    assert exc.value.status_code == 403
    assert "admin token" in exc.value.detail


def test_post_to_x_uses_browser_session_without_admin(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }
    session_id, _ = create_x_session(
        {
            "oauth_token": "browser-token",
            "oauth_token_secret": "browser-secret",
            "screen_name": "browser_user",
            "user_id": "123",
        }
    )
    calls = []

    async def fake_create_x_post(text, session, media_id=None):
        calls.append((text, session["oauth_token"], media_id))
        return {"posted": True, "id": "post-123", "url": "https://x.com/browser_user/status/post-123"}

    async def fail_oauth2(*args, **kwargs):
        pytest.fail("server OAuth2 token should not be used when a browser session exists")

    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))
    monkeypatch.setattr(x_api, "create_x_post", fake_create_x_post)
    monkeypatch.setattr(x_api, "create_x_post_oauth2", fail_oauth2)

    class Request:
        cookies = {X_OAUTH_COOKIE_NAME: session_id}
        headers = {}

    result = asyncio.run(api.post_to_x(Request(), XPostRequest(text="draft")))

    assert result["posted"] is True
    assert result["screen_name"] == "browser_user"
    assert calls == [("draft", "browser-token", None)]
    X_OAUTH_SESSIONS.clear()


def test_top_sword_post_falls_back_to_link_when_media_upload_disabled(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "X_SCREEN_NAME": "joewilsonai",
        "X_MEDIA_UPLOAD_ENABLED": "false",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }
    posted = {}

    class Request:
        cookies = {}
        headers = {"Authorization": "Bearer admin-token"}

    async def fake_create_x_post_oauth2(text, access_token, media_id=None):
        posted["text"] = text
        posted["access_token"] = access_token
        posted["media_id"] = media_id
        return {
            "posted": True,
            "id": "post-123",
            "text": text,
            "url": "https://x.com/joewilsonai/status/post-123",
            "media_id": media_id,
        }

    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))
    monkeypatch.setattr(api, "fetch_daily_slate_rows", lambda date, limit: [SAMPLE_ROWS[0]])
    monkeypatch.setattr(x_api, "create_x_post_oauth2", fake_create_x_post_oauth2)
    monkeypatch.setattr(x_api, "upload_and_post_top_sword_video", lambda *args, **kwargs: pytest.fail("native upload should not run"))

    result = asyncio.run(api.post_top_sword_to_x(Request(), TopSwordPostRequest(date="2026-05-06")))

    assert result["posted"] is True
    assert result["post_mode"] == "link"
    assert result["media_upload_enabled"] is False
    assert posted["access_token"] == "access-token"
    assert posted["media_id"] is None
    assert "https://swordfinder.com/api/watch/top-sword?date=2026-05-06&rank=1" in posted["text"]


def test_top_sword_post_requires_admin_token(monkeypatch):
    env = {
        "X_OAUTH2_ACCESS_TOKEN": "access-token",
        "X_SCREEN_NAME": "joewilsonai",
        "SWORDFINDER_ADMIN_TOKEN": "admin-token",
    }

    class Request:
        cookies = {}
        headers = {}

    monkeypatch.setattr(x_api, "get_env", lambda name, default=None: env.get(name, default))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.post_top_sword_to_x(Request(), TopSwordPostRequest(date="2026-05-06")))

    assert exc.value.status_code == 403
    assert "admin token" in exc.value.detail


def test_oauth2_video_upload_uses_v2_media_endpoints(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, files=None, data=None):
            calls.append({"method": "POST", "url": url, "headers": headers, "json": json, "files": files, "data": data})
            if url.endswith("/initialize"):
                return Response(200, {"data": {"id": "media-123"}})
            if url.endswith("/append"):
                return Response(200, {"data": {"expires_at": 123}})
            if url.endswith("/finalize"):
                return Response(200, {"data": {"id": "media-123"}})
            raise AssertionError(f"unexpected POST {url}")

        async def get(self, url, headers=None, params=None):
            calls.append({"method": "GET", "url": url, "headers": headers, "params": params})
            return Response(200, {"data": {"id": "media-123"}})

    monkeypatch.setattr(x_api.httpx, "AsyncClient", Client)

    result = asyncio.run(x_api.upload_x_video_bytes_oauth2(b"video-bytes", "video/mp4", "oauth2-token"))

    assert result["media_id"] == "media-123"
    assert calls[0]["url"] == "https://api.x.com/2/media/upload/initialize"
    assert calls[0]["headers"]["Authorization"] == "Bearer oauth2-token"
    assert calls[0]["json"]["media_category"] == "tweet_video"
    assert calls[1]["url"] == "https://api.x.com/2/media/upload/media-123/append"
    assert calls[1]["files"]["media"][1] == b"video-bytes"
    assert calls[2]["url"] == "https://api.x.com/2/media/upload/media-123/finalize"


def test_oauth2_video_upload_polls_v2_status_by_media_id(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, files=None, data=None):
            calls.append({"method": "POST", "url": url, "headers": headers, "json": json, "files": files, "data": data})
            if url.endswith("/initialize"):
                return Response(200, {"data": {"id": "media-123"}})
            if url.endswith("/append"):
                return Response(200, {"data": {"expires_at": 123}})
            if url.endswith("/finalize"):
                return Response(200, {"data": {"id": "media-123", "processing_info": {"state": "pending", "check_after_secs": 1}}})
            raise AssertionError(f"unexpected POST {url}")

        async def get(self, url, headers=None, params=None):
            calls.append({"method": "GET", "url": url, "headers": headers, "params": params})
            return Response(200, {"data": {"id": "media-123", "processing_info": {"state": "succeeded"}}})

    async def noop_sleep(seconds):
        return None

    monkeypatch.setattr(x_api.httpx, "AsyncClient", Client)
    monkeypatch.setattr(x_api.asyncio, "sleep", noop_sleep)

    result = asyncio.run(x_api.upload_x_video_bytes_oauth2(b"video-bytes", "video/mp4", "oauth2-token"))
    status_calls = [call for call in calls if call["method"] == "GET"]

    assert result["media_id"] == "media-123"
    assert status_calls[0]["url"] == "https://api.x.com/2/media/upload"
    assert status_calls[0]["params"] == {"media_id": "media-123"}


def test_upload_x_video_retries_init_without_media_category_after_forbidden(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = text

        def json(self):
            return self._payload

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, data=None, files=None, json=None):
            calls.append({"url": url, "data": data, "files": files})
            if data and data.get("command") == "INIT":
                init_calls = [call for call in calls if call["data"] and call["data"].get("command") == "INIT"]
                if len(init_calls) == 1:
                    return Response(403, text="")
                return Response(200, {"media_id_string": "media-123"})
            if data and data.get("command") == "FINALIZE":
                return Response(200, {})
            return Response(204, {})

        async def get(self, url, headers=None):
            return Response(200, {})

    monkeypatch.setattr(x_api.httpx, "AsyncClient", Client)
    monkeypatch.setattr(x_api, "x_user_auth_header", lambda *args, **kwargs: "OAuth test")

    result = asyncio.run(
        x_api.upload_x_video_bytes(
            b"video-bytes",
            "video/mp4",
            {"oauth_token": "token", "oauth_token_secret": "secret"},
        )
    )

    init_calls = [call for call in calls if call["data"] and call["data"].get("command") == "INIT"]
    assert result["media_id"] == "media-123"
    assert init_calls[0]["data"]["media_category"] == "tweet_video"
    assert "media_category" not in init_calls[1]["data"]


def test_parse_oauth_form_response_reads_token_fields():
    parsed = parse_oauth_form_response(
        "oauth_token=request-token&oauth_token_secret=request-secret&oauth_callback_confirmed=true"
    )

    assert parsed["oauth_token"] == "request-token"
    assert parsed["oauth_token_secret"] == "request-secret"
    assert parsed["oauth_callback_confirmed"] == "true"


def test_oauth1_authorization_header_contains_signature_and_token():
    header = build_oauth1_authorization_header(
        "POST",
        "https://api.x.com/2/tweets",
        "consumer-key",
        "consumer-secret",
        token="user-token",
        token_secret="user-secret",
    )

    assert header.startswith("OAuth ")
    assert 'oauth_consumer_key="consumer-key"' in header
    assert 'oauth_token="user-token"' in header
    assert "oauth_signature=" in header


def test_validate_x_post_text_rejects_empty_and_over_limit():
    assert validate_x_post_text(" hello ") == "hello"

    with pytest.raises(Exception):
        validate_x_post_text(" ")

    with pytest.raises(Exception):
        validate_x_post_text("x" * 281)


def test_x_safe_return_to_allows_swordfinder_and_rejects_other_hosts():
    assert x_safe_return_to("https://swordfinder.com/?date=2026-05-06") == (
        "https://swordfinder.com/?date=2026-05-06"
    )
    assert x_safe_return_to("https://evil.example/?date=2026-05-06") == "https://swordfinder.com"


def test_x_oauth_authorize_url_targets_x_authorization():
    assert x_oauth_authorize_url("request-token") == (
        "https://api.x.com/oauth/authorize?oauth_token=request-token"
    )


def test_store_x_oauth_request_tracks_request_secret_and_return(monkeypatch):
    X_OAUTH_REQUESTS.clear()
    monkeypatch.setattr("api_services.x_sharing.time.time", lambda: 1000)

    token = store_x_oauth_request(
        {"oauth_token": "request-token", "oauth_token_secret": "request-secret"},
        return_to="https://swordfinder.com/?date=2026-05-06",
    )

    assert token == "request-token"
    assert X_OAUTH_REQUESTS["request-token"]["oauth_token_secret"] == "request-secret"
    assert X_OAUTH_REQUESTS["request-token"]["return_to"] == "https://swordfinder.com/?date=2026-05-06"
    assert X_OAUTH_REQUESTS["request-token"]["created_at"] == 1000


def test_prune_x_oauth_requests_removes_expired_tokens():
    X_OAUTH_REQUESTS.clear()
    X_OAUTH_REQUESTS["fresh"] = {"created_at": 1000}
    X_OAUTH_REQUESTS["expired"] = {"created_at": 1}

    prune_x_oauth_requests(now=1100)

    assert "fresh" in X_OAUTH_REQUESTS
    assert "expired" not in X_OAUTH_REQUESTS


def test_create_x_session_stores_access_tokens_without_exposing_cookie_value():
    X_OAUTH_SESSIONS.clear()

    session_id, session = create_x_session(
        {
            "oauth_token": "access-token",
            "oauth_token_secret": "access-secret",
            "screen_name": "SwordFinder",
            "user_id": "123",
        }
    )

    assert session_id in X_OAUTH_SESSIONS
    assert session["screen_name"] == "SwordFinder"
    assert X_OAUTH_SESSIONS[session_id]["oauth_token_secret"] == "access-secret"
