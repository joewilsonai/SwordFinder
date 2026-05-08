#!/usr/bin/env python3
"""
Process sword videos for regular-season games only (smart mode).
Skips dates that already have videos processed.
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


def get_known_opening_day(year):
    return KNOWN_OPENING_DAYS.get(year, datetime(year, 3, 25))


def check_date_already_processed(date_str, supabase):
    """Check if we already have videos for this date"""
    result = supabase.table('mlb_pitches_enhanced')\
        .select('id')\
        .eq('game_date', date_str)\
        .not_.is_('video_azure_blob_url', 'null')\
        .limit(1)\
        .execute()
    
    return len(result.data) > 0

def process_videos_for_date(date_str, supabase, video_processor, n_videos=5):
    """Process top N videos for a specific date (REGULAR SEASON ONLY)"""
    
    # Check if already processed
    if check_date_already_processed(date_str, supabase):
        logger.info(f"⏭️  Skipping {date_str} - already has videos")
        return 0
    
    # Query top swords for this date - REGULAR SEASON ONLY
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq('game_date', date_str)\
        .eq('game_type', 'R')\
        .gte('sword_score', MIN_VIDEO_SWORD_SCORE)\
        .order('sword_score', desc=True)\
        .limit(20)\
        .execute()
    
    if not result.data:
        logger.info(f"No regular season sword swings found for {date_str}")
        return 0
    
    df = pd.DataFrame(result.data)
    logger.info(f"Found {len(df)} regular season sword candidates for {date_str}")
    
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
            player_name_safe = str(pitch['player_name']).replace(' ', '_').replace('/', '_')
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


def parse_args():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    parser = argparse.ArgumentParser(description="Smart processor for regular-season sword videos.")
    parser.add_argument('--season-year', type=int, default=datetime.now().year)
    parser.add_argument('--start-date', type=str, default=None)
    parser.add_argument('--end-date', type=str, default=yesterday)
    parser.add_argument('--videos-per-day', type=int, default=5)
    parser.add_argument('--dry-run', action='store_true', help='Print plan only.')
    return parser.parse_args()


def main():
    """Process regular-season sword videos only and skip already-processed dates."""
    args = parse_args()
    load_dotenv()

    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')

    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return

    supabase = create_client(supabase_url, supabase_key)
    video_processor = EnhancedSwordVideoProcessor()

    print("🗡️ SwordFinder Regular Season Video Processor (SMART)")
    print("=" * 50)

    season_start = args.start_date or f"{args.season_year}-01-01"
    season_end = f"{args.season_year + 1}-01-01"

    existing = supabase.table('mlb_pitches_enhanced')\
        .select('game_date')\
        .eq('game_type', 'R')\
        .gte('game_date', season_start)\
        .lt('game_date', season_end)\
        .not_.is_('video_azure_blob_url', 'null')\
        .execute()

    processed_dates = set()
    if existing.data:
        processed_dates = set(row['game_date'] for row in existing.data)
        print(f"\n✅ Already processed {len(processed_dates)} dates with {len(existing.data)} videos")
        latest_date = max(processed_dates)
        print(f"📅 Latest processed date: {latest_date}")
        start_date = datetime.strptime(latest_date, '%Y-%m-%d') + timedelta(days=1)
    else:
        result = supabase.table('mlb_pitches_enhanced')\
            .select('game_date')\
            .eq('game_type', 'R')\
            .gte('game_date', season_start)\
            .lt('game_date', season_end)\
            .order('game_date')\
            .limit(1)\
            .execute()

        if result.data:
            start_date = datetime.strptime(result.data[0]['game_date'], '%Y-%m-%d')
        else:
            start_date = get_known_opening_day(args.season_year)

    if args.start_date:
        manual_start = datetime.strptime(args.start_date, '%Y-%m-%d')
        if manual_start > start_date:
            start_date = manual_start

    end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    if start_date > end_date:
        print(f"No work to do: start date {start_date.date()} is after end date {end_date.date()}.")
        return

    print(f"\n📅 Processing from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    total_days = (end_date - start_date).days + 1
    total_videos = len(existing.data) if existing.data else 0
    days_with_videos = len(processed_dates) if existing.data else 0
    skipped = 0

    if args.dry_run:
        print("🧪 Dry run complete. No videos were processed.")
        print(f"   - Days in range: {total_days}")
        print(f"   - Existing processed dates in-season: {len(processed_dates)}")
        print(f"   - Videos/day target: {args.videos_per_day}")
        return

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"\n📅 Processing {date_str}...")

        videos = process_videos_for_date(
            date_str,
            supabase,
            video_processor,
            n_videos=args.videos_per_day,
        )
        if videos == 0 and check_date_already_processed(date_str, supabase):
            skipped += 1
        else:
            total_videos += videos
            if videos > 0:
                days_with_videos += 1

        current_date += timedelta(days=1)

        days_done = (current_date - start_date).days
        print(f"Progress: {days_done}/{total_days} days, {total_videos} videos total ({skipped} skipped)")

    print("\n" + "=" * 50)
    print("✅ Regular Season Processing Complete!")
    print(f"   - Days processed: {total_days - skipped}")
    print(f"   - Days skipped: {skipped}")
    print(f"   - Total videos: {total_videos}")
    if days_with_videos > 0:
        print(f"   - Average per day: {total_videos/days_with_videos:.1f}")

if __name__ == "__main__":
    main() 
