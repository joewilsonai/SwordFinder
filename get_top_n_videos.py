#!/usr/bin/env python3
"""
Get top N sword swing videos, skipping any without play IDs.
Guarantees N videos (or all available if fewer exist).
"""

import argparse
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from clean_video_processor import EnhancedSwordVideoProcessor
from get_play_ids_on_demand import get_play_ids_for_pitches

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resolve_scores_csv(year: int, input_file: str = None) -> str:
    """Resolve input CSV path with explicit support for historical files."""
    if input_file:
        return input_file

    candidate = Path(f"mlb_{year}_with_sword_scores.csv")
    if candidate.exists():
        return str(candidate)

    # Backward compatibility: 2025 historical dataset.
    legacy = Path("mlb_2025_with_sword_scores.csv")
    if year == 2025 and legacy.exists():
        return str(legacy)

    raise FileNotFoundError(
        f"No score CSV found for {year}. Expected {candidate.name}. "
        "Use --input-file to override."
    )


def get_top_n_sword_videos(
    date_str,
    n_videos=5,
    max_attempts=20,
    input_file=None,
    dry_run=False,
):
    """
    Get exactly n_videos sword swings, skipping any without play IDs.
    """
    target_date = pd.to_datetime(date_str).date()
    csv_year = target_date.year
    scores_file = resolve_scores_csv(csv_year, input_file=input_file)

    print(f"🗡️ Getting Top {n_videos} Sword Videos for {target_date}")
    print("=" * 60)
    print(f"📄 Source CSV: {scores_file}")

    print("📊 Loading data with sword scores...")
    df = pd.read_csv(scores_file, low_memory=False)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date

    date_swords = df[
        (df["game_date"] == target_date) & (df["sword_score"].notna())
    ].sort_values("sword_score", ascending=False)

    if date_swords.empty:
        print(f"❌ No sword swings found for {target_date}")
        return 0

    print(f"📊 Found {len(date_swords)} total sword swings for {target_date}")

    if dry_run:
        print("🧪 Dry run complete. No video downloads were attempted.")
        return 0

    video_dir = f"sword_videos_{str(target_date).replace('-', '')}_guaranteed"
    os.makedirs(video_dir, exist_ok=True)
    video_processor = EnhancedSwordVideoProcessor()

    downloaded_count = 0
    checked_count = 0
    batch_size = 5

    print(f"\n🎯 Goal: Download {n_videos} videos (checking up to {max_attempts} swings)")
    print("-" * 60)

    while downloaded_count < n_videos and checked_count < min(len(date_swords), max_attempts):
        batch_start = checked_count
        batch_end = min(checked_count + batch_size, len(date_swords))
        batch = date_swords.iloc[batch_start:batch_end]

        if batch.empty:
            break

        print(f"\n📡 Checking batch {batch_start + 1}-{batch_end} for play IDs...")
        batch_with_ids = get_play_ids_for_pitches(batch)

        for i in range(len(batch_with_ids)):
            if downloaded_count >= n_videos:
                break

            pitch = batch_with_ids.iloc[i]
            rank = checked_count + i + 1
            bat_speed = pitch.get("bat_speed")
            bat_speed_str = f"{bat_speed:.1f}" if pd.notna(bat_speed) else "N/A"
            print(
                f"\n{rank}. {pitch.get('player_name')} - "
                f"Score: {pitch.get('sword_score', 0):.1f} ({bat_speed_str} mph)"
            )

            if pd.notna(pitch.get("mlb_play_id", None)):
                player_name_safe = str(pitch.get("player_name", "unknown")).replace(" ", "_")
                filename = (
                    f"{video_dir}/{downloaded_count + 1}_{player_name_safe}_"
                    f"score{pitch['sword_score']:.0f}_rank{rank}.mp4"
                )

                video_url = video_processor.get_video_url_for_play(
                    str(pitch.get("game_pk", "")),
                    pitch["mlb_play_id"],
                )

                if video_url:
                    success = video_processor.download_video_locally(video_url, filename)
                    if success:
                        downloaded_count += 1
                        print(f"   ✅ Downloaded #{downloaded_count}: {filename}")
                    else:
                        print("   ❌ Failed to download video")
                else:
                    print("   ❌ No video URL found")
            else:
                print("   ⚠️  No play ID - skipping to next")

        checked_count = batch_end

        if downloaded_count < n_videos:
            print(
                f"\n📊 Progress: {downloaded_count}/{n_videos} videos downloaded, "
                f"{checked_count} swings checked"
            )

    print("\n" + "=" * 60)
    print(f"📊 Final Summary for {target_date}:")
    print(f"   - Total sword swings: {len(date_swords)}")
    print(f"   - Swings checked: {checked_count}")
    print(f"   - Videos downloaded: {downloaded_count}")
    print(f"   - Videos saved to: {video_dir}/")

    if downloaded_count == n_videos:
        print(f"\n✅ Success! Got all {n_videos} requested videos!")
    elif downloaded_count > 0:
        print(f"\n⚠️  Only found {downloaded_count} videos out of {n_videos} requested")
    else:
        print("\n❌ No videos could be downloaded")

    return downloaded_count


def parse_args():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="Fetch top sword videos for a date.")
    parser.add_argument("date", nargs="?", default=yesterday, help="Target date (YYYY-MM-DD)")
    parser.add_argument("n_videos", nargs="?", default=5, type=int, help="Number of videos")
    parser.add_argument("--max-attempts", type=int, default=20)
    parser.add_argument("--input-file", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Validate input and counts only.")
    return parser.parse_args()


def main():
    args = parse_args()
    get_top_n_sword_videos(
        args.date,
        n_videos=args.n_videos,
        max_attempts=args.max_attempts,
        input_file=args.input_file,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
