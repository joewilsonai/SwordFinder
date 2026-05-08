#!/usr/bin/env python3
"""Backfill missing videos for date-selectable daily top sword slates."""

import argparse
import asyncio
import logging
from typing import Optional

from api import (
    MIN_PUBLIC_SWORD_SCORE,
    fetch_daily_slate_rows,
    find_missing_video_rows,
    hydrate_missing_daily_slate_videos,
    supabase,
    validate_slate_date,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def filter_dates(
    dates: list,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list:
    filtered = []
    for date in dates:
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        filtered.append(date)
    return filtered


def build_daily_backfill_summary(date: str, rows: list) -> dict:
    missing = find_missing_video_rows(rows)
    return {
        "date": date,
        "count": len(rows),
        "pending": len(missing),
        "pending_players": [
            row.get("batter_name") or row.get("player_name") or "Unknown hitter"
            for row in missing
        ],
    }


def fetch_regular_season_sword_dates(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list:
    all_rows = []
    offset = 0
    page_size = 1000

    while True:
        query = supabase.table("mlb_pitches_enhanced")\
            .select("game_date")\
            .eq("game_type", "R")\
            .gte("sword_score", MIN_PUBLIC_SWORD_SCORE)\
            .order("game_date")

        if start_date:
            query = query.gte("game_date", start_date)
        if end_date:
            query = query.lte("game_date", end_date)

        result = query.range(offset, offset + page_size - 1).execute()
        page = result.data or []
        all_rows.extend(page)

        if len(page) < page_size:
            break
        offset += page_size

    return sorted({row["game_date"] for row in all_rows if row.get("game_date")})


async def backfill_daily_slates(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5,
    dry_run: bool = False,
) -> dict:
    dates = fetch_regular_season_sword_dates(start_date=start_date, end_date=end_date)
    dates = filter_dates(dates, start_date=start_date, end_date=end_date)

    total_pending = 0
    total_processed = 0
    summaries = []

    logging.info("Checking %s daily slates (limit=%s, dry_run=%s)", len(dates), limit, dry_run)

    for date in dates:
        rows = fetch_daily_slate_rows(date, limit)
        summary = build_daily_backfill_summary(date, rows)
        summaries.append(summary)

        if summary["pending"] == 0:
            continue

        total_pending += summary["pending"]
        logging.info(
            "%s has %s pending top-slate clips: %s",
            date,
            summary["pending"],
            ", ".join(summary["pending_players"]),
        )

        if dry_run:
            continue

        processed = await hydrate_missing_daily_slate_videos(rows, date)
        total_processed += processed

        refreshed = build_daily_backfill_summary(date, fetch_daily_slate_rows(date, limit))
        logging.info(
            "%s processed=%s remaining=%s",
            date,
            processed,
            refreshed["pending"],
        )

    return {
        "dates_checked": len(dates),
        "total_pending": total_pending,
        "total_processed": total_processed,
        "dry_run": dry_run,
        "summaries": summaries,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Backfill daily top-slate SwordFinder videos")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Top N slate rows per day to check. Defaults to homepage top 5.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report backlog without processing")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.start_date:
        validate_slate_date(args.start_date)
    if args.end_date:
        validate_slate_date(args.end_date)

    limit = max(1, min(args.limit, 25))
    result = asyncio.run(
        backfill_daily_slates(
            start_date=args.start_date,
            end_date=args.end_date,
            limit=limit,
            dry_run=args.dry_run,
        )
    )

    logging.info(
        "Backfill complete: dates=%s pending_seen=%s processed=%s dry_run=%s",
        result["dates_checked"],
        result["total_pending"],
        result["total_processed"],
        result["dry_run"],
    )


if __name__ == "__main__":
    main()
