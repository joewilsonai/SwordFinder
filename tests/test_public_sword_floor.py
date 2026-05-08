from pathlib import Path

from api import MIN_PUBLIC_SWORD_SCORE
from process_daily_sword_videos import parse_args as parse_daily_args
from process_season_video_backlog import parse_args


def test_public_sword_floor_is_ninety_points():
    assert MIN_PUBLIC_SWORD_SCORE == 90.0


def test_public_ui_filters_out_sub_ninety_scores():
    sources = [
        Path("ui/assets/index.js").read_text(),
        Path("ui/assets/leaderboards.js").read_text(),
        Path("ui/assets/ops.js").read_text(),
    ]

    for source in sources:
        assert "sword_score: 'gte.90'" in source
        assert "sword_score: 'gt.0'" not in source


def test_season_video_backlog_defaults_to_ninety_point_floor():
    args = parse_args([])

    assert args.min_score == 90.0


def test_daily_video_worker_defaults_to_ninety_point_floor(monkeypatch):
    monkeypatch.delenv("VIDEO_MIN_SWORD_SCORE", raising=False)

    args = parse_daily_args([])

    assert args.min_score == 90.0
