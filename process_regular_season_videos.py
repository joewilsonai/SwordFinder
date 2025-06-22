#!/usr/bin/env python3
"""
Process sword videos for REGULAR SEASON only (excluding spring training)
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv
from get_play_ids_on_demand import get_play_ids_for_pitches
from clean_video_processor import EnhancedSwordVideoProcessor
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_regular_season_start():
    """Get the start date of regular season from database"""
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    supabase = create_client(supabase_url, supabase_key)
    
    # Find first regular season game (game_type = 'R')
    result = supabase.table('mlb_pitches_enhanced')\
        .select('game_date')\
        .eq('game_type', 'R')\
        .order('game_date')\
        .limit(1)\
        .execute()
    
    if result.data:
        return datetime.strptime(result.data[0]['game_date'], '%Y-%m-%d')
    else:
        # Default to April 1 if not found
        return datetime(2025, 4, 1)

def process_videos_for_date(date_str, supabase, video_processor, n_videos=5):
    """Process top N videos for a specific date (REGULAR SEASON ONLY)"""
    
    # Query top swords for this date - REGULAR SEASON ONLY
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq('game_date', date_str)\
        .eq('game_type', 'R')\
        .gt('sword_score', 0)\
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

def main():
    """Process regular season sword videos only"""
    load_dotenv()
    
    # Initialize
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    video_processor = EnhancedSwordVideoProcessor()
    
    print("🗡️ SwordFinder Regular Season Video Processor")
    print("=" * 50)
    
    # Get regular season start date
    print("\n📅 Finding regular season start date...")
    start_date = get_regular_season_start()
    end_date = datetime(2025, 6, 21)
    
    print(f"Regular season: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    total_days = (end_date - start_date).days + 1
    total_videos = 0
    days_with_videos = 0
    
    # Process each day
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"\n📅 Processing {date_str}...")
        
        videos = process_videos_for_date(date_str, supabase, video_processor)
        total_videos += videos
        if videos > 0:
            days_with_videos += 1
        
        current_date += timedelta(days=1)
        
        # Progress update
        days_done = (current_date - start_date).days
        print(f"Progress: {days_done}/{total_days} days, {total_videos} videos total")
    
    # Summary
    print("\n" + "=" * 50)
    print("✅ Regular Season Processing Complete!")
    print(f"   - Days processed: {total_days}")
    print(f"   - Days with videos: {days_with_videos}")
    print(f"   - Total videos: {total_videos}")
    if days_with_videos > 0:
        print(f"   - Average per day: {total_videos/days_with_videos:.1f}")
    
    # Get some stats from database
    stats = supabase.table('mlb_pitches_enhanced')\
        .select('sword_score')\
        .not_.is_('video_azure_blob_url', 'null')\
        .execute()
    
    if stats.data:
        print(f"\n📊 Database Stats:")
        print(f"   - Videos in Azure: {len(stats.data)}")

if __name__ == "__main__":
    main() 