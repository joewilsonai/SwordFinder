#!/usr/bin/env python3
"""Drain uncached high-score SwordFinder videos across a season."""

import argparse
import logging
import time
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from env_config import get_env
from process_daily_sword_videos import process_videos_for_swords


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def fetch_pending_rows(
    supabase,
    start_date: str,
    end_date: str,
    min_score: float,
    limit: int,
) -> list:
    result = supabase.table("mlb_pitches_enhanced")\
        .select("*")\
        .eq("game_type", "R")\
        .gte("game_date", start_date)\
        .lte("game_date", end_date)\
        .gte("sword_score", min_score)\
        .is_("video_azure_blob_url", "null")\
        .order("sword_score", desc=True)\
        .limit(limit)\
        .execute()

    return result.data or []


def group_rows_by_date(rows: list) -> dict:
    grouped = {}
    for row in rows:
        game_date = row.get("game_date")
        if not game_date:
            continue
        grouped.setdefault(game_date, []).append(row)
    return grouped


def process_backlog(
    start_date: str,
    end_date: str,
    min_score: float,
    limit: int,
    batch_size: int,
    pause_seconds: float,
    dry_run: bool = False,
) -> dict:
    load_dotenv()

    supabase_url = get_env("SUPABASE_URL")
    supabase_key = get_env("SUPABASE_SERVICE_ROLE_KEY") or get_env("SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing Supabase credentials")

    supabase = create_client(supabase_url, supabase_key)
    pending_rows = fetch_pending_rows(
        supabase=supabase,
        start_date=start_date,
        end_date=end_date,
        min_score=min_score,
        limit=limit,
    )
    rows_by_date = group_rows_by_date(pending_rows)

    logging.info(
        "Found %s uncached regular-season videos at score >= %.1f across %s dates",
        len(pending_rows),
        min_score,
        len(rows_by_date),
    )

    if dry_run:
        for game_date, rows in sorted(rows_by_date.items()):
            logging.info("%s pending=%s", game_date, len(rows))
        return {
            "pending": len(pending_rows),
            "processed": 0,
            "dates": len(rows_by_date),
            "dry_run": True,
        }

    processed_total = 0
    attempted_total = 0
    for game_date, rows in sorted(rows_by_date.items()):
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            attempted_total += len(batch)
            logging.info(
                "Processing %s rows %s-%s of %s",
                game_date,
                start + 1,
                start + len(batch),
                len(rows),
            )
            processed = process_videos_for_swords(pd.DataFrame(batch), game_date)
            processed_total += processed
            logging.info(
                "%s batch processed=%s attempted_total=%s processed_total=%s",
                game_date,
                processed,
                attempted_total,
                processed_total,
            )
            if pause_seconds > 0:
                time.sleep(pause_seconds)

    return {
        "pending": len(pending_rows),
        "processed": processed_total,
        "dates": len(rows_by_date),
        "dry_run": False,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Drain high-score SwordFinder video backlog")
    parser.add_argument("--start-date", default="2026-01-01", type=validate_date)
    parser.add_argument("--end-date", default="2026-12-31", type=validate_date)
    parser.add_argument("--min-score", type=float, default=90.0)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    result = process_backlog(
        start_date=args.start_date,
        end_date=args.end_date,
        min_score=args.min_score,
        limit=max(1, args.limit),
        batch_size=max(1, args.batch_size),
        pause_seconds=max(0, args.pause_seconds),
        dry_run=args.dry_run,
    )
    logging.info(
        "Backlog run complete: pending_seen=%s processed=%s dates=%s dry_run=%s",
        result["pending"],
        result["processed"],
        result["dates"],
        result["dry_run"],
    )


if __name__ == "__main__":
    main()
