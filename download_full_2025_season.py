#!/usr/bin/env python3
"""
Download full MLB season data.

This file keeps the legacy name for backward compatibility, but now supports
dynamic season years and a dry-run mode for safer validation.
"""

import argparse
import os
from datetime import datetime
from typing import Optional

import pandas as pd
import pybaseball

# MLB opening-day map used for deterministic seasonal backfills.
KNOWN_OPENING_DAYS = {
    2025: "2025-03-20",
    2026: "2026-03-25",
}


def get_opening_day(year: int) -> str:
    """Return known opening day for a season, with a safe fallback."""
    return KNOWN_OPENING_DAYS.get(year, f"{year}-03-25")


def download_full_season(
    year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_file: Optional[str] = None,
    dry_run: bool = False,
):
    """Download complete season data for the selected year."""
    if year is None:
        year = datetime.now().year

    resolved_start = start_date or get_opening_day(year)
    resolved_end = end_date or datetime.now().strftime("%Y-%m-%d")
    resolved_output = output_file or f"mlb_{year}_full_season_complete.csv"

    if resolved_start > resolved_end:
        raise ValueError(f"start_date {resolved_start} is after end_date {resolved_end}")

    print(f"⚾ FULL {year} MLB SEASON DOWNLOAD")
    print("=" * 60)
    print(f"📅 Season range: {resolved_start} to {resolved_end}")
    print(f"💾 Output file: {resolved_output}")

    if dry_run:
        print("\n🧪 Dry run complete. No data downloaded.")
        return pd.DataFrame()

    print("\n⏱️ This may take a few minutes depending on date range...")
    print("📥 Downloading from MLB Statcast...")
    df = pybaseball.statcast(start_dt=resolved_start, end_dt=resolved_end)

    print(f"\n✅ Downloaded {len(df):,} pitches!")
    print(f"📊 Data has {len(df.columns)} columns")

    print("\n🏷️ Adding query helper flags...")
    df["is_home_run"] = df["events"] == "home_run"
    df["is_strikeout"] = df["events"] == "strikeout"
    df["is_walk"] = df["events"].isin(["walk", "intent_walk"])
    df["is_hit"] = df["events"].isin(["single", "double", "triple", "home_run"])
    df["is_extra_base_hit"] = df["events"].isin(["double", "triple", "home_run"])
    df["is_whiff"] = df["description"].isin(["swinging_strike", "swinging_strike_blocked"])
    df["is_sword_candidate"] = (
        (df["strikes"] == 2) & (df["events"] == "strikeout") & df["is_whiff"]
    )
    df["is_true_sword"] = (
        df["is_sword_candidate"] & (df["bat_speed"] < 60) & (df["swing_path_tilt"] > 30)
    )
    df["is_100_plus"] = df["release_speed"] >= 100

    print(f"\n💾 Saving to {resolved_output}...")
    df.to_csv(resolved_output, index=False)
    file_size = os.path.getsize(resolved_output) / (1024 * 1024)

    print("\n📊 SEASON SUMMARY:")
    print(f"   Total pitches: {len(df):,}")
    print(f"   Unique games: {df['game_pk'].nunique():,}")
    print(f"   Home runs: {df['is_home_run'].sum():,}")
    print(f"   Strikeouts: {df['is_strikeout'].sum():,}")
    print(f"   100+ mph pitches: {df['is_100_plus'].sum():,}")

    if df["bat_speed"].notna().sum() > 0:
        print("\n🏏 BAT TRACKING STATS:")
        print(f"   Swings tracked: {df['bat_speed'].notna().sum():,}")
        print(f"   Avg bat speed: {df['bat_speed'].mean():.1f} mph")
        print(f"   Sword candidates: {df['is_sword_candidate'].sum():,}")
        print(f"   True sword swings: {df['is_true_sword'].sum():,}")

    print(f"\n📁 File size: {file_size:.1f} MB")
    print(f"✅ Saved to: {resolved_output}")
    print("\n🎯 READY TO QUERY!")
    print("Examples:")
    print(f"   df = pd.read_csv('{resolved_output}')")
    print("   df[df['is_home_run']].groupby(pd.to_datetime(df['game_date']).dt.month).apply(")
    print("       lambda x: x.nlargest(5, 'hit_distance_sc'))")

    return df


def download_full_2025_season():
    """Legacy helper retained for backward compatibility."""
    return download_full_season(year=2025)


def parse_args():
    parser = argparse.ArgumentParser(description="Download full MLB season Statcast data.")
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--start-date", type=str, default=None)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--output-file", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print resolved settings only.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    download_full_season(
        year=args.year,
        start_date=args.start_date,
        end_date=args.end_date,
        output_file=args.output_file,
        dry_run=args.dry_run,
    )
