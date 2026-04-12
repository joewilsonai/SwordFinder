#!/usr/bin/env python3
"""
Process all sword videos for an MLB season.
- Upload sword scores to Supabase
- Download top N videos per day
- Upload to Azure and update database
"""

import argparse
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

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


def get_known_opening_day(year):
    return KNOWN_OPENING_DAYS.get(year, datetime(year, 3, 25))


def resolve_scores_csv(year, csv_path=None):
    if csv_path:
        return csv_path
    candidate = Path(f"mlb_{year}_with_sword_scores.csv")
    if candidate.exists():
        return str(candidate)
    if year == 2025 and Path("mlb_2025_with_sword_scores.csv").exists():
        return "mlb_2025_with_sword_scores.csv"
    raise FileNotFoundError(
        f"Expected score CSV {candidate.name} was not found. Use --scores-csv to override."
    )


def upload_sword_scores_to_supabase(scores_csv, dry_run=False):
    """Upload all sword scores from CSV to Supabase."""
    load_dotenv()

    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')

    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return False

    supabase = create_client(supabase_url, supabase_key)

    logger.info("📊 Loading CSV with sword scores...")
    logger.info(f"Using score file: {scores_csv}")
    df = pd.read_csv(scores_csv, low_memory=False)

    sword_df = df[df['sword_score'].notna()].copy()
    logger.info(f"Found {len(sword_df)} sword candidates to update")

    if dry_run:
        logger.info("🧪 Dry run enabled. Skipping Supabase sword score updates.")
        return True

    batch_size = 100
    updated = 0

    for i in range(0, len(sword_df), batch_size):
        batch = sword_df.iloc[i:i + batch_size]

        try:
            for _, row in batch.iterrows():
                result = supabase.table('mlb_pitches_enhanced')\
                    .update({
                        'sword_score': float(row['sword_score']),
                        'is_sword_candidate': True,
                        'is_true_sword': float(row['sword_score']) >= 80
                    })\
                    .eq('game_pk', int(row['game_pk']))\
                    .eq('at_bat_number', int(row['at_bat_number']))\
                    .eq('pitch_number', int(row['pitch_number']))\
                    .execute()

                updated += 1

            logger.info(f"Updated {updated}/{len(sword_df)} sword scores")

        except Exception as e:
            logger.error(f"Error updating batch: {e}")

    logger.info(f"✅ Finished updating {updated} sword scores")
    return True

def process_videos_for_date(date_str, supabase, video_processor, n_videos=5):
    """Process top N videos for a specific date"""
    
    # Query top swords for this date
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq('game_date', date_str)\
        .gt('sword_score', 0)\
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


def parse_args():
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    parser = argparse.ArgumentParser(description="Process season sword videos.")
    parser.add_argument('--season-year', type=int, default=datetime.now().year)
    parser.add_argument('--scores-csv', type=str, default=None)
    parser.add_argument('--start-date', type=str, default=None)
    parser.add_argument('--end-date', type=str, default=yesterday)
    parser.add_argument('--videos-per-day', type=int, default=5)
    parser.add_argument('--skip-score-upload', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Print plan only.')
    return parser.parse_args()


def main():
    """Process all sword videos for the selected season."""
    args = parse_args()
    load_dotenv()

    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')

    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return

    supabase = create_client(supabase_url, supabase_key)
    video_processor = EnhancedSwordVideoProcessor()

    print("🗡️ SwordFinder Season Video Processor")
    print("=" * 50)

    try:
        scores_csv = resolve_scores_csv(args.season_year, args.scores_csv)
    except FileNotFoundError as exc:
        if args.dry_run:
            scores_csv = args.scores_csv or f"mlb_{args.season_year}_with_sword_scores.csv"
            print(f"⚠️  {exc}")
        else:
            raise
    start_date = (
        datetime.strptime(args.start_date, '%Y-%m-%d')
        if args.start_date
        else get_known_opening_day(args.season_year)
    )
    end_date = datetime.strptime(args.end_date, '%Y-%m-%d')

    if start_date > end_date:
        print(f"No work to do: start date {start_date.date()} is after end date {end_date.date()}.")
        return

    total_days = (end_date - start_date).days + 1

    if args.dry_run:
        print("🧪 Dry run complete. No score updates or video processing executed.")
        print(f"   - Season year: {args.season_year}")
        print(f"   - Score CSV: {scores_csv}")
        print(f"   - Start date: {start_date.date()}")
        print(f"   - End date: {end_date.date()}")
        print(f"   - Days in range: {total_days}")
        print(f"   - Videos/day target: {args.videos_per_day}")
        return

    if not args.skip_score_upload:
        print("\n📊 Step 1: Uploading sword scores to Supabase...")
        if not upload_sword_scores_to_supabase(scores_csv, dry_run=args.dry_run):
            print("❌ Failed to upload scores. Exiting.")
            return
    else:
        print("\n⏭️ Skipping score upload (--skip-score-upload)")

    print("\n📹 Step 2: Processing videos for each day...")
    total_videos = 0
    days_with_videos = 0

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
        total_videos += videos
        if videos > 0:
            days_with_videos += 1

        current_date += timedelta(days=1)

        days_done = (current_date - start_date).days
        print(f"Progress: {days_done}/{total_days} days, {total_videos} videos total")

    print("\n" + "=" * 50)
    print("✅ Season Processing Complete!")
    print(f"   - Days processed: {total_days}")
    print(f"   - Days with videos: {days_with_videos}")
    print(f"   - Total videos: {total_videos}")
    if days_with_videos > 0:
        print(f"   - Average per day: {total_videos/days_with_videos:.1f}")

    stats = supabase.table('mlb_pitches_enhanced')\
        .select('sword_score')\
        .not_.is_('video_azure_blob_url', 'null')\
        .execute()

    if stats.data:
        print(f"\n📊 Database Stats:")
        print(f"   - Videos in Azure: {len(stats.data)}")

if __name__ == "__main__":
    main() 
