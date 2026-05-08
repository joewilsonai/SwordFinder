from backfill_daily_slate_videos import build_daily_backfill_summary, filter_dates


def test_filter_dates_keeps_only_requested_range():
    dates = ["2026-03-25", "2026-04-01", "2026-05-06"]

    assert filter_dates(dates, start_date="2026-04-01", end_date="2026-05-01") == [
        "2026-04-01"
    ]


def test_build_daily_backfill_summary_counts_missing_top_slate_videos():
    summary = build_daily_backfill_summary(
        "2026-05-06",
        [
            {
                "batter_name": "Corey Seager",
                "player_name": "De Los Santos, Yerry",
                "video_azure_blob_url": "https://example.test/clip.mp4",
            },
            {
                "batter_name": "Mickey Moniak",
                "player_name": "Raley, Brooks",
                "video_azure_blob_url": None,
            },
        ],
    )

    assert summary == {
        "date": "2026-05-06",
        "count": 2,
        "pending": 1,
        "pending_players": ["Mickey Moniak"],
    }
