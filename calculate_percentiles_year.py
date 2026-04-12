#!/usr/bin/env python3
"""
Calculate percentile fields for a single season year and upsert to Supabase.

This script is intended as a reliable fallback when server-side SQL window
updates time out.
"""

import argparse
import logging
from math import sqrt

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from env_config import get_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


SELECT_FIELDS = [
    "id",
    "game_date",
    "pitch_type",
    "release_speed",
    "release_spin_rate",
    "pfx_x",
    "pfx_z",
    "bat_speed",
    "sword_score",
    "release_extension",
    "perceived_velocity",
]

UPDATE_FIELDS = [
    "movement_total",
    "velo_percentile_overall",
    "velo_percentile_pitch_type",
    "spin_percentile_overall",
    "spin_percentile_pitch_type",
    "movement_percentile_overall",
    "movement_percentile_pitch_type",
    "bat_speed_percentile_overall",
    "bat_speed_percentile_sword",
    "extension_percentile_overall",
    "extension_percentile_pitch_type",
    "perceived_velo_percentile_overall",
    "perceived_velo_percentile_pitch_type",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate percentiles for one season year and upsert to Supabase."
    )
    parser.add_argument("--year", type=int, required=True, help="Season year (example: 2026)")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Rows per upsert request (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute values but skip database writes.",
    )
    return parser.parse_args()


def percentile_rank(series: pd.Series) -> pd.Series:
    """0..100 percentile rank for non-null values."""
    ranked = series.rank(method="max", pct=True)
    return ranked * 100.0


def to_nullable_float(value):
    if pd.isna(value):
        return None
    return float(value)


def load_year_rows(supabase, year: int) -> pd.DataFrame:
    logger.info("Loading rows for %s", year)
    all_rows = []
    last_id = None
    page_size = 5000

    while True:
        query = (
            supabase.table("mlb_pitches_enhanced")
            .select(",".join(SELECT_FIELDS))
            .gte("game_date", f"{year}-01-01")
            .lt("game_date", f"{year + 1}-01-01")
            .order("id")
        )
        if last_id is not None:
            query = query.gt("id", last_id)
        result = query.range(0, page_size - 1).execute()

        if not result.data:
            break

        all_rows.extend(result.data)
        last_id = result.data[-1]["id"]
        logger.info("Loaded %s rows so far", len(all_rows))

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df

    # Ensure deterministic numeric dtypes where possible.
    for col in [
        "release_speed",
        "release_spin_rate",
        "pfx_x",
        "pfx_z",
        "bat_speed",
        "sword_score",
        "release_extension",
        "perceived_velocity",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def compute_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Computing movement and percentile fields")

    # Derived metric
    df["movement_total"] = np.sqrt((df["pfx_x"] ** 2) + (df["pfx_z"] ** 2))

    # Velocity
    df["velo_percentile_overall"] = percentile_rank(df["release_speed"])
    df["velo_percentile_pitch_type"] = df.groupby("pitch_type")["release_speed"].transform(
        percentile_rank
    )

    # Spin
    df["spin_percentile_overall"] = percentile_rank(df["release_spin_rate"])
    df["spin_percentile_pitch_type"] = df.groupby("pitch_type")["release_spin_rate"].transform(
        percentile_rank
    )

    # Movement
    df["movement_percentile_overall"] = percentile_rank(df["movement_total"])
    df["movement_percentile_pitch_type"] = df.groupby("pitch_type")["movement_total"].transform(
        percentile_rank
    )

    # Bat speed overall (only valid swings)
    valid_bat = df["bat_speed"] > 0
    df.loc[valid_bat, "bat_speed_percentile_overall"] = percentile_rank(
        df.loc[valid_bat, "bat_speed"]
    )

    # Sword-specific inverted percentile (lower bat speed = worse => higher percentile)
    sword_mask = (df["bat_speed"] > 0) & (df["sword_score"] > 0)
    sword_pct = percentile_rank(df.loc[sword_mask, "bat_speed"])
    df.loc[sword_mask, "bat_speed_percentile_sword"] = 100.0 - sword_pct

    # Extension
    df["extension_percentile_overall"] = percentile_rank(df["release_extension"])
    df["extension_percentile_pitch_type"] = df.groupby("pitch_type")["release_extension"].transform(
        percentile_rank
    )

    # Perceived velocity (if present for season)
    if df["perceived_velocity"].notna().any():
        df["perceived_velo_percentile_overall"] = percentile_rank(df["perceived_velocity"])
        df["perceived_velo_percentile_pitch_type"] = df.groupby("pitch_type")[
            "perceived_velocity"
        ].transform(percentile_rank)

    return df


def upsert_updates(supabase, df: pd.DataFrame, batch_size: int, dry_run: bool) -> None:
    rows = []
    for _, row in df.iterrows():
        payload = {"id": int(row["id"])}
        for field in UPDATE_FIELDS:
            payload[field] = to_nullable_float(row.get(field))
        rows.append(payload)

    logger.info("Prepared %s upsert rows", len(rows))
    if dry_run:
        logger.info("Dry run enabled, skipping database writes")
        return

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        supabase.table("mlb_pitches_enhanced").upsert(chunk).execute()
        logger.info("Upserted %s/%s", min(i + batch_size, len(rows)), len(rows))


def main() -> None:
    args = parse_args()
    load_dotenv()

    supabase_url = get_env("SUPABASE_URL")
    supabase_key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise SystemExit("Missing Supabase credentials")

    supabase = create_client(supabase_url, supabase_key)

    print("📊 Year-Scoped Percentile Calculator")
    print("=" * 50)
    print(f"🎯 Season year: {args.year}")
    if args.dry_run:
        print("🧪 Dry run: enabled")

    df = load_year_rows(supabase, args.year)
    if df.empty:
        print(f"No rows found for {args.year}. Nothing to do.")
        return

    print(f"Loaded {len(df):,} rows for {args.year}")

    df = compute_percentiles(df)
    upsert_updates(supabase, df, batch_size=args.batch_size, dry_run=args.dry_run)

    print("✅ Percentile update complete")


if __name__ == "__main__":
    main()
