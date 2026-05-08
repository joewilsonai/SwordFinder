#!/usr/bin/env python3
"""
Process top sword videos per day (skips score upload).
Supports dynamic season defaults and dry-run validation.
"""

import argparse
import logging
import os
import time
from datetime import datetime, timedelta

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from clean_video_processor import EnhancedSwordVideoProcessor
from env_config import get_env
from get_play_ids_on_demand import get_play_ids_for_pitches

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KNOWN_OPENING_DAYS = {
    2025: datetime(2025, 3, 20),
    2026: datetime(2026, 3, 25),
}
MIN_VIDEO_SWORD_SCORE = 90.0


def get_default_start_date(season_year):
    return KNOWN_OPENING_DAYS.get(season_year, datetime(season_year, 3, 25))


def process_videos_for_date(date_str, supabase, video_processor, n_videos=5):
    """Process top N videos for a specific date"""
    
    # Query top swords for this date
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq('game_date', date_str)\
        .gte('sword_score', MIN_VIDEO_SWORD_SCORE)\
        .order('sword_score', desc=True)\
        .limit(20)\
        .execute()
    
    if not result.data:
        logger.info(f"No sword swings found for {date_str}")
        return 0
    
    df = pd.DataFrame(result.data)
    logger.info(f"Found {len(df)} sword candidates for {date_str}")
    
    # Get play IDs
    df_with_ids = get_play_ids_for_pitches(df)
    
    # Process videos
    processed = 0
    checked = 0
    
    for _, pitch in df_with_ids.iterrows():
        if processed >= n_videos:
            break
            
        checked += 1
        
        if pitch.get('mlb_play_id') is not None and str(pitch.get('mlb_play_id')).strip():
            # Create filename
            player_name_safe = str(pitch['player_name']).replace(' ', '_')
            date_clean = date_str.replace('-', '')
            filename = f"sword_{date_clean}_{player_name_safe}_{pitch['sword_score']:.0f}.mp4"
            blob_name = f"sword_videos/{date_clean}/{filename}"
            
            logger.info(f"Processing: {pitch['player_name']} ({pitch['sword_score']:.1f})")
            
            # Get video URL
            video_url = video_processor.get_video_url_for_play(
                str(pitch['game_pk']), 
                pitch['mlb_play_id']
            )
            
            if video_url:
                # Upload to Azure
                azure_url = video_processor.upload_video_to_azure(video_url, blob_name)
                
                if azure_url:
                    # Update database with Azure URL
                    supabase.table('mlb_pitches_enhanced')\
                        .update({
                            'video_azure_blob_url': azure_url,
                            'video_processed_at': datetime.now().isoformat()
                        })\
                        .eq('id', pitch['id'])\
                        .execute()
                    
                    processed += 1
                    logger.info(f"✅ Processed video {processed}/{n_videos}")
                else:
                    logger.warning(f"Failed to upload to Azure")
            else:
                logger.warning(f"No video URL found")
        
        # Don't overwhelm MLB servers
        time.sleep(2)
    
    logger.info(f"Processed {processed} videos for {date_str} (checked {checked} candidates)")
    return processed


def parse_cli_args():
    yesterday = datetime.now() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Process top sword videos by date/date-range.")
    parser.add_argument(
        "--mode",
        choices=["interactive", "last7", "specific", "range", "season"],
        default="interactive",
    )
    parser.add_argument("--season-year", type=int, default=datetime.now().year)
    parser.add_argument("--date", type=str, default=None, help="Specific date for --mode specific")
    parser.add_argument("--start-date", type=str, default=None, help="Start date for --mode range")
    parser.add_argument("--end-date", type=str, default=yesterday.strftime("%Y-%m-%d"))
    parser.add_argument("--videos-per-day", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="Print planned dates only.")
    return parser.parse_args()


def build_dates_from_args(args):
    dates_to_process = []
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    if args.mode == "last7":
        for i in range(7):
            date = end_date - timedelta(days=i)
            dates_to_process.append(date.strftime("%Y-%m-%d"))
    elif args.mode == "specific":
        if not args.date:
            raise ValueError("--date is required for --mode specific")
        dates_to_process.append(args.date)
    elif args.mode == "range":
        if not args.start_date:
            raise ValueError("--start-date is required for --mode range")
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        current = start_date
        while current <= end_date:
            dates_to_process.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
    elif args.mode == "season":
        current = get_default_start_date(args.season_year)
        while current <= end_date:
            dates_to_process.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
    else:
        # interactive mode handled elsewhere
        pass

    return dates_to_process


def interactive_dates(season_year):
    print("\nOptions:")
    print("1. Process last 7 days")
    print("2. Process specific date (e.g., 2026-04-10)")
    print("3. Process date range")
    print("4. Process full season to yesterday")

    choice = input("\nEnter choice (1-4): ").strip()
    dates_to_process = []
    yesterday = datetime.now() - timedelta(days=1)

    if choice == "1":
        for i in range(7):
            date = yesterday - timedelta(days=i)
            dates_to_process.append(date.strftime("%Y-%m-%d"))
    elif choice == "2":
        date_str = input("Enter date (YYYY-MM-DD): ").strip()
        dates_to_process.append(date_str)
    elif choice == "3":
        start_str = input("Enter start date (YYYY-MM-DD): ").strip()
        end_str = input("Enter end date (YYYY-MM-DD): ").strip()
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_str, "%Y-%m-%d")

        current = start_date
        while current <= end_date:
            dates_to_process.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
    else:
        current = get_default_start_date(season_year)
        while current <= yesterday:
            dates_to_process.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

    return dates_to_process


def main():
    """Process videos for a date range or specific dates."""
    args = parse_cli_args()

    if args.mode == "interactive":
        dates_to_process = interactive_dates(args.season_year)
    else:
        dates_to_process = build_dates_from_args(args)

    if not dates_to_process:
        print("No dates selected.")
        return

    if args.dry_run:
        print("🧪 Dry run complete. Planned date processing:")
        print(f"   - Dates: {len(dates_to_process)}")
        print(f"   - First date: {dates_to_process[0]}")
        print(f"   - Last date: {dates_to_process[-1]}")
        print(f"   - Videos per day: {args.videos_per_day}")
        return

    load_dotenv()

    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')

    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return

    supabase = create_client(supabase_url, supabase_key)
    video_processor = EnhancedSwordVideoProcessor()

    print("🗡️ SwordFinder Video Processor (Videos Only)")
    print("=" * 50)

    total_videos = 0
    print(f"\n📹 Processing {len(dates_to_process)} days...")

    for date_str in dates_to_process:
        print(f"\n📅 Processing {date_str}...")
        videos = process_videos_for_date(
            date_str,
            supabase,
            video_processor,
            n_videos=args.videos_per_day,
        )
        total_videos += videos

        print(
            f"Progress: {dates_to_process.index(date_str)+1}/{len(dates_to_process)} days, "
            f"{total_videos} videos total"
        )

    print("\n" + "=" * 50)
    print("✅ Processing Complete!")
    print(f"   - Days processed: {len(dates_to_process)}")
    print(f"   - Total videos: {total_videos}")
    if total_videos > 0:
        print(f"   - Average per day: {total_videos/len(dates_to_process):.1f}")


if __name__ == "__main__":
    main()
