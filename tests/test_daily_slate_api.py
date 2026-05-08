import pytest
from fastapi import HTTPException

from api import (
    build_daily_slate_response,
    clamp_daily_slate_limit,
    find_missing_video_rows,
    validate_slate_date,
)


def test_daily_slate_limit_is_capped_for_public_hydration():
    assert clamp_daily_slate_limit(0) == 1
    assert clamp_daily_slate_limit(3) == 3
    assert clamp_daily_slate_limit(25) == 5


def test_validate_slate_date_requires_date_only_format():
    assert validate_slate_date("2026-05-06") == "2026-05-06"

    with pytest.raises(HTTPException) as exc:
        validate_slate_date("2026-05-06T00:00:00Z")

    assert exc.value.status_code == 400


def test_find_missing_video_rows_only_returns_blank_clip_rows():
    rows = [
        {"id": 1, "video_azure_blob_url": "https://example.test/clip.mp4"},
        {"id": 2, "video_azure_blob_url": None},
        {"id": 3, "video_azure_blob_url": ""},
    ]

    assert [row["id"] for row in find_missing_video_rows(rows)] == [2, 3]


def test_build_daily_slate_response_normalizes_and_counts_pending_rows():
    response = build_daily_slate_response(
        date="2026-05-06",
        limit=5,
        rows=[
            {
                "id": 1,
                "batter_name": "Corey Seager",
                "pitcher_name": "De Los Santos, Yerry",
                "player_name": "De Los Santos, Yerry",
                "video_azure_blob_url": "https://example.test/clip.mp4",
            },
            {
                "id": 2,
                "batter_name": "Mickey Moniak",
                "pitcher_name": "Raley, Brooks",
                "player_name": "Raley, Brooks",
                "video_azure_blob_url": None,
            },
        ],
        hydrated=1,
    )

    assert response["date"] == "2026-05-06"
    assert response["limit"] == 5
    assert response["hydrated"] == 1
    assert response["pending_videos"] == 1
    assert response["last_checked"].endswith("Z")
    assert response["rows"][0]["player_name"] == "Corey Seager"
