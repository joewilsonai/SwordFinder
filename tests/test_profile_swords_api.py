from pathlib import Path

import pytest
from fastapi import HTTPException

from api import (
    PROFILE_SWORD_MAX_LIMIT,
    build_profile_swords_response,
    clamp_profile_limit,
    profile_filter_column,
    validate_profile_date_range,
)


def test_profile_limit_is_capped_for_public_hydration():
    assert clamp_profile_limit(0) == 1
    assert clamp_profile_limit(25) == 25
    assert clamp_profile_limit(999) == PROFILE_SWORD_MAX_LIMIT


def test_profile_kind_maps_to_safe_filter_columns():
    assert profile_filter_column("pitcher") == "pitcher"
    assert profile_filter_column("batter") == "batter"
    assert profile_filter_column("player") == "batter"

    with pytest.raises(HTTPException) as exc:
        profile_filter_column("team")

    assert exc.value.status_code == 400


def test_profile_date_range_requires_valid_forward_dates():
    assert validate_profile_date_range("2026-04-01", "2026-05-01") == (
        "2026-04-01",
        "2026-05-01",
    )

    with pytest.raises(HTTPException) as exc:
        validate_profile_date_range("2026-05-01", "2026-04-01")

    assert exc.value.status_code == 400


def test_build_profile_swords_response_normalizes_and_counts_pending_videos():
    response = build_profile_swords_response(
        profile_kind="pitcher",
        entity_id=571578,
        limit=80,
        rows=[
            {
                "id": 1,
                "batter_name": "David Hamilton",
                "pitcher_name": "Corbin, Patrick",
                "player_name": "Corbin, Patrick",
                "video_azure_blob_url": "https://example.test/clip.mp4",
            },
            {
                "id": 2,
                "batter_name": "Brice Turang",
                "pitcher_name": "Corbin, Patrick",
                "player_name": "Corbin, Patrick",
                "video_azure_blob_url": None,
            },
        ],
        total_pitches=452,
        hydrated=1,
    )

    assert response["profile_kind"] == "pitcher"
    assert response["entity_id"] == 571578
    assert response["total_pitches"] == 452
    assert response["hydrated"] == 1
    assert response["pending_videos"] == 1
    assert response["rows"][0]["player_name"] == "David Hamilton"
    assert response["rows"][0]["pitcher_name"] == "Corbin, Patrick"


def test_profile_pages_use_hydrating_profile_api():
    pitcher_source = Path("ui/assets/pitcher.js").read_text()
    player_source = Path("ui/assets/player.js").read_text()

    assert "/profiles/pitcher/${pitcherId}/swords" in pitcher_source
    assert "/profiles/batter/${playerId}/swords" in player_source
    assert "ensure_videos: 'true'" in pitcher_source
    assert "ensure_videos: 'true'" in player_source
    assert "fetchRows" not in pitcher_source
    assert "fetchRows" not in player_source
