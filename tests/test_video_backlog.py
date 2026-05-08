import pandas as pd

from api import build_video_backlog_status, normalize_video_backlog_row
from process_daily_sword_videos import select_video_backlog_rows


def test_select_video_backlog_rows_limits_by_score_by_default():
    rows = pd.DataFrame(
        [
            {"id": 1, "sword_score": 80.0},
            {"id": 2, "sword_score": 110.0},
            {"id": 3, "sword_score": 95.0},
        ]
    )

    selected = select_video_backlog_rows(rows, top_n=2, process_all=False)

    assert selected["id"].tolist() == [2, 3]


def test_select_video_backlog_rows_can_return_all_ranked_rows():
    rows = pd.DataFrame(
        [
            {"id": 1, "sword_score": 80.0},
            {"id": 2, "sword_score": 110.0},
            {"id": 3, "sword_score": 95.0},
        ]
    )

    selected = select_video_backlog_rows(rows, top_n=1, process_all=True)

    assert selected["id"].tolist() == [2, 3, 1]


def test_normalize_video_backlog_row_uses_hitter_name_and_pending_status():
    row = {
        "id": 760130,
        "batter_name": "Jonny DeLuca",
        "pitcher_name": "Gage, Matt",
        "player_name": "Gage, Matt",
        "video_azure_blob_url": None,
    }

    normalized = normalize_video_backlog_row(row)

    assert normalized["player_name"] == "Jonny DeLuca"
    assert normalized["pitcher_name"] == "Gage, Matt"
    assert normalized["video_status"] == "pending"


def test_build_video_backlog_status_calculates_counts_and_ratio():
    status = build_video_backlog_status(
        date="2026-05-03",
        total_swords=12,
        cached_videos=9,
        pending_rows=[
            {
                "id": 760130,
                "batter_name": "Jonny DeLuca",
                "pitcher_name": "Gage, Matt",
                "player_name": "Gage, Matt",
                "video_azure_blob_url": None,
            }
        ],
    )

    assert status["date"] == "2026-05-03"
    assert status["total_swords"] == 12
    assert status["cached_videos"] == 9
    assert status["pending_videos"] == 3
    assert status["cache_rate"] == 0.75
    assert status["last_checked"].endswith("Z")
    assert status["top_pending"][0]["player_name"] == "Jonny DeLuca"
