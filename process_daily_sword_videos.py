#!/usr/bin/env python3
"""
Process videos for yesterday's top sword swings
Runs after the daily data update to download and upload videos
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
import logging
from get_play_ids_on_demand import get_play_ids_for_pitches
from clean_video_processor import EnhancedSwordVideoProcessor as MLBVideoProcessor
from env_config import get_env

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_processing.log'),
        logging.StreamHandler()
    ]
)


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def select_video_backlog_rows(df: pd.DataFrame, top_n: int = 10, process_all: bool = False):
    """Rank pending video rows and return either the top N or the full backlog."""
    if df.empty:
        return df

    ranked = df.sort_values("sword_score", ascending=False)
    if process_all:
        return ranked
    return ranked.head(min(top_n, len(ranked)))


def get_yesterdays_top_swords(
    supabase,
    date_str: str,
    top_n: int = 10,
    process_all: bool = False,
):
    """Get pending regular-season sword video rows for a date."""

    fetch_limit = 1000 if process_all else top_n * 2

    # Only get regular season games (game_type = 'R') as spring training has no videos
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq('game_date', date_str)\
        .eq('game_type', 'R')\
        .not_.is_('sword_score', 'null')\
        .gt('sword_score', 0)\
        .is_('video_azure_blob_url', 'null')\
        .order('sword_score', desc=True)\
        .limit(fetch_limit)\
        .execute()
    
    if not result.data:
        logging.warning(f"No sword candidates found for {date_str}")
        return pd.DataFrame()
    
    df = pd.DataFrame(result.data)
    logging.info(f"Found {len(df)} sword candidates for {date_str}")
    
    return select_video_backlog_rows(df, top_n=top_n, process_all=process_all)

def process_videos_for_swords(df: pd.DataFrame, date_str: str):
    """Download and process videos for sword swings"""
    
    if df.empty:
        return 0
    
    # Get play IDs
    logging.info(f"Fetching play IDs for {len(df)} swings...")
    df_with_ids = get_play_ids_for_pitches(df)
    
    # Count how many have play IDs
    has_play_id = df_with_ids['mlb_play_id'].notna().sum()
    logging.info(f"Found play IDs for {has_play_id}/{len(df)} swings")
    
    if has_play_id == 0:
        return 0
    
    # Initialize processors
    video_processor = MLBVideoProcessor()
    load_dotenv()
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY') or get_env('SUPABASE_ANON_KEY')
    
    if not supabase_url or not supabase_key:
        logging.error("Missing Supabase credentials")
        return 0
    
    supabase = create_client(supabase_url, supabase_key)
    processed_count = 0
    
    # Process each video
    for _, pitch in df_with_ids.iterrows():
        if not pitch.get('mlb_play_id'):
            continue
        
        try:
            # Create filename
            player_name = str(pitch.get('player_name', 'unknown')).replace(' ', '_')
            bat_speed = pitch.get('bat_speed', 0)
            video_filename = f"sword_{date_str}_{player_name}_{bat_speed:.1f}mph.mp4"
            
            logging.info(f"Processing video for {pitch.get('player_name')} ({bat_speed:.1f} mph)")
            
            # Get video URL first
            game_pk = str(pitch.get('game_pk', ''))
            play_id = str(pitch['mlb_play_id'])
            video_url = video_processor.get_video_url_for_play(game_pk, play_id)
            
            if video_url:
                # Direct upload to Azure (streams from URL)
                blob_name = f"swords/{date_str}/{video_filename}"
                azure_url = video_processor.upload_video_to_azure(video_url, blob_name)
                
                if azure_url:
                    # Update database using unique ID if available
                    if pitch.get('id'):
                        # Preferred: update by unique ID
                        update_result = supabase.table('mlb_pitches_enhanced').update({
                            'video_azure_blob_url': azure_url,
                            'video_processed_at': datetime.now().isoformat()
                        }).eq('id', pitch.get('id')).execute()
                    else:
                        # Fallback: use composite key
                        update_result = supabase.table('mlb_pitches_enhanced').update({
                            'video_azure_blob_url': azure_url,
                            'video_processed_at': datetime.now().isoformat()
                        }).eq('game_pk', pitch.get('game_pk'))\
                         .eq('at_bat_number', pitch.get('at_bat_number'))\
                         .eq('pitch_number', pitch.get('pitch_number'))\
                         .execute()
                    
                    processed_count += 1
                    logging.info(f"✅ Video uploaded: {azure_url}")
            else:
                logging.warning(f"Failed to get video URL for play {play_id}")
                
        except Exception as e:
            logging.error(f"Error processing video: {e}")
    
    return processed_count

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Process pending SwordFinder videos")
    parser.add_argument(
        "--date",
        help="Date to process in YYYY-MM-DD format. Defaults to PROCESS_DATE_OVERRIDE or yesterday.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=parse_positive_int(os.getenv("VIDEO_TOP_N"), 10),
        help="Number of pending sword clips to process when not using --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=parse_bool(os.getenv("VIDEO_PROCESS_ALL", "false")),
        help="Process the full pending video backlog for the date, capped by the Supabase read limit.",
    )
    return parser.parse_args(argv)


def resolve_target_date(args):
    if args.date:
        return args.date

    date_override = os.getenv("PROCESS_DATE_OVERRIDE")
    if date_override:
        return date_override

    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')


def main(argv=None):
    """Main execution"""
    args = parse_args(argv)
    logging.info("Starting daily sword video processing...")
    date_str = resolve_target_date(args)

    logging.info(
        "Processing videos for %s (top_n=%s, process_all=%s)",
        date_str,
        args.top_n,
        args.all,
    )
    
    # Load environment
    load_dotenv()
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY') or get_env('SUPABASE_ANON_KEY')
    
    if not supabase_url or not supabase_key:
        logging.error("Missing Supabase credentials")
        sys.exit(1)
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Get pending video rows
    top_swords = get_yesterdays_top_swords(
        supabase,
        date_str,
        top_n=args.top_n,
        process_all=args.all,
    )
    
    if top_swords.empty:
        logging.info("No sword swings to process")
        return
    
    # Log top swords
    logging.info(f"\nTop sword swings for {date_str}:")
    for _, sword in top_swords.head().iterrows():
        logging.info(f"  {sword.get('player_name')}: {sword.get('bat_speed', 0):.1f} mph (score: {sword.get('sword_score', 0):.1f})")
    
    # Process videos
    processed = process_videos_for_swords(top_swords, date_str)
    
    logging.info(f"\n✅ Video processing complete! Processed {processed} videos for {date_str}")
    
    # Summary
    if processed > 0:
        # Query to see how many total videos we have
        video_result = supabase.table('mlb_pitches_enhanced')\
            .select('id')\
            .not_.is_('video_azure_blob_url', 'null')\
            .execute()
        
        logging.info(f"Total videos in database: {len(video_result.data)}")

if __name__ == "__main__":
    main()
