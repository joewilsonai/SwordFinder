import asyncio
import pytest

import api
from api import (
    ShareDraftRequest,
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
    x_safe_return_to,
    X_OAUTH_REQUESTS,
    X_OAUTH_SESSIONS,
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
    assert "https://swordfinder.com/?date=2026-05-06" in text
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


def test_x_oauth_status_reports_disabled_while_full_oauth_is_rebuilt():
    class Request:
        cookies = {}

    status = asyncio.run(api.x_oauth_status(Request()))

    assert api.X_SHARING_ENABLED is False
    assert status["configured"] is False
    assert status["connected"] is False
    assert status["disabled"] is True
    assert "full OAuth" in status["message"]


def test_x_draft_endpoint_is_disabled_before_external_calls():
    with pytest.raises(api.HTTPException) as exc:
        asyncio.run(api.draft_x_post(ShareDraftRequest(date="2026-05-06")))

    assert exc.value.status_code == 503
    assert "temporarily disabled" in exc.value.detail


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

    monkeypatch.setattr(api.httpx, "AsyncClient", Client)
    monkeypatch.setattr(api, "x_user_auth_header", lambda *args, **kwargs: "OAuth test")

    result = asyncio.run(
        api.upload_x_video_bytes(
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
    monkeypatch.setattr("api.time.time", lambda: 1000)

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
