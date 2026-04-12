#!/usr/bin/env python3
"""
Backfill SwordFinder data for the selected MLB season year.

Default behavior targets the current season from opening day through yesterday.
"""

import argparse
import logging
from datetime import datetime, timedelta

import pandas as pd
from pybaseball import statcast
from dotenv import load_dotenv
from supabase import create_client

from daily_update import (
    calculate_perceived_velocity_simple,
    calculate_strike_zone_distance_simple,
    calculate_sword_candidates,
    upload_to_supabase,
)
from env_config import get_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KNOWN_OPENING_DAYS = {
    2025: datetime(2025, 3, 20),
    2026: datetime(2026, 3, 25),
}


def get_opening_day(year):
    return KNOWN_OPENING_DAYS.get(year, datetime(year, 3, 25))


def parse_args():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="Backfill season data into mlb_pitches_enhanced.")
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date", type=str, default=yesterday)
    parser.add_argument("--dry-run", action="store_true", help="Show what would be loaded.")
    return parser.parse_args()


def fetch_and_prepare_date(date_str):
    logger.info("Fetching Statcast data for %s", date_str)
    df = statcast(start_dt=date_str, end_dt=date_str, verbose=False)

    if df is None or df.empty:
        logger.info("No pitches returned for %s", date_str)
        return None

    df = calculate_sword_candidates(df)

    if "release_extension" in df.columns and "release_speed" in df.columns:
        df["perceived_velocity"] = df.apply(
            lambda row: calculate_perceived_velocity_simple(
                row["release_speed"], row["release_extension"]
            ),
            axis=1,
        )

    if all(col in df.columns for col in ["plate_x", "plate_z", "sz_top", "sz_bot"]):
        df["strike_zone_distance_inches"] = df.apply(
            lambda row: calculate_strike_zone_distance_simple(
                row["plate_x"], row["plate_z"], row["sz_top"], row["sz_bot"]
            ),
            axis=1,
        )

    return df


def get_existing_pitch_keys(supabase, date_str, batch_size=1000):
    """Fetch existing composite pitch keys for one game date."""
    keys = set()
    offset = 0

    while True:
        result = (
            supabase.table("mlb_pitches_enhanced")
            .select("game_pk,at_bat_number,pitch_number")
            .eq("game_date", date_str)
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        rows = result.data or []
        if not rows:
            break

        for row in rows:
            key = (
                int(row["game_pk"]),
                int(row["at_bat_number"]),
                int(row["pitch_number"]),
            )
            keys.add(key)

        if len(rows) < batch_size:
            break
        offset += batch_size

    return keys


def drop_existing_rows(df, existing_keys):
    """Drop rows already present in Supabase using pitch composite keys."""
    if not existing_keys:
        return df

    key_series = list(
        zip(
            pd.to_numeric(df["game_pk"], errors="coerce").fillna(-1).astype(int),
            pd.to_numeric(df["at_bat_number"], errors="coerce").fillna(-1).astype(int),
            pd.to_numeric(df["pitch_number"], errors="coerce").fillna(-1).astype(int),
        )
    )
    mask_new = [k not in existing_keys for k in key_series]
    return df.loc[mask_new].copy()


def main():
    args = parse_args()
    load_dotenv()
    supabase_url = get_env("SUPABASE_URL")
    supabase_key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    supabase = create_client(supabase_url, supabase_key)

    start_dt = (
        datetime.strptime(args.start_date, "%Y-%m-%d")
        if args.start_date
        else get_opening_day(args.year)
    )
    end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")

    if start_dt > end_dt:
        print(f"No work to do: start date {start_dt.date()} is after end date {end_dt.date()}.")
        return

    print("⚾ SwordFinder Season Backfill")
    print("=" * 50)
    print(f"Season year: {args.year}")
    print(f"Date range: {start_dt.date()} to {end_dt.date()}")
    print(f"Dry run: {args.dry_run}")

    dates_total = (end_dt - start_dt).days + 1
    dates_checked = 0
    dates_skipped_existing = 0
    dates_no_games = 0
    dates_no_new_rows = 0
    dates_loaded = 0
    pitches_loaded = 0

    current = start_dt
    while current <= end_dt:
        date_str = current.strftime("%Y-%m-%d")
        dates_checked += 1
        logger.info("Processing %s (%d/%d)", date_str, dates_checked, dates_total)

        df = fetch_and_prepare_date(date_str)
        if df is None or df.empty:
            dates_no_games += 1
            current += timedelta(days=1)
            continue

        existing_keys = get_existing_pitch_keys(supabase, date_str)
        if existing_keys:
            before = len(df)
            df = drop_existing_rows(df, existing_keys)
            dropped = before - len(df)
            if dropped > 0:
                logger.info("Dropped %d already-existing rows for %s", dropped, date_str)

        if df.empty:
            dates_skipped_existing += 1
            dates_no_new_rows += 1
            current += timedelta(days=1)
            continue

        if args.dry_run:
            pitches_loaded += len(df)
            dates_loaded += 1
            logger.info("Dry run: would upload %d pitches for %s", len(df), date_str)
            current += timedelta(days=1)
            continue

        success = upload_to_supabase(df)
        if not success:
            logger.error("Upload failed for %s. Continuing to next date.", date_str)
        else:
            dates_loaded += 1
            pitches_loaded += len(df)
            logger.info("Uploaded %d pitches for %s", len(df), date_str)

        current += timedelta(days=1)

    print("\n✅ Backfill Summary")
    print(f"   - Dates in range: {dates_total}")
    print(f"   - Dates checked: {dates_checked}")
    print(f"   - Dates skipped (already present): {dates_skipped_existing}")
    print(f"   - Dates with no new rows after dedupe: {dates_no_new_rows}")
    print(f"   - Dates with no games/data: {dates_no_games}")
    print(f"   - Dates loaded: {dates_loaded}")
    print(f"   - Pitches loaded: {pitches_loaded:,}")


if __name__ == "__main__":
    main()
