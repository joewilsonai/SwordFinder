import pytest

from api import (
    ShareDraftRequest,
    build_x_share_text,
    build_x_post_page_url,
    build_x_post_prompt,
    build_xai_chat_payload,
    extract_xai_draft,
    trim_x_post_text,
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
