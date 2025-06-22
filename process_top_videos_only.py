#!/usr/bin/env python3
"""
Process only top 5 videos per day (skips score upload)
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

def main():
    """Process videos for a date range or specific dates"""
    load_dotenv()
    
    # Initialize
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    video_processor = EnhancedSwordVideoProcessor()
    
    print("🗡️ SwordFinder Video Processor (Videos Only)")
    print("=" * 50)
    
    # Option to process specific dates or date range
    print("\nOptions:")
    print("1. Process last 7 days")
    print("2. Process specific date (e.g., 2025-06-20)")
    print("3. Process date range")
    print("4. Process full season (March 20 - June 21)")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    dates_to_process = []
    
    if choice == "1":
        # Last 7 days
        end_date = datetime(2025, 6, 21)
        for i in range(7):
            date = end_date - timedelta(days=i)
            dates_to_process.append(date.strftime('%Y-%m-%d'))
    
    elif choice == "2":
        # Specific date
        date_str = input("Enter date (YYYY-MM-DD): ").strip()
        dates_to_process.append(date_str)
    
    elif choice == "3":
        # Date range
        start_str = input("Enter start date (YYYY-MM-DD): ").strip()
        end_str = input("Enter end date (YYYY-MM-DD): ").strip()
        start_date = datetime.strptime(start_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_str, '%Y-%m-%d')
        
        current = start_date
        while current <= end_date:
            dates_to_process.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
    
    else:
        # Full season
        start_date = datetime(2025, 3, 20)
        end_date = datetime(2025, 6, 21)
        
        current = start_date
        while current <= end_date:
            dates_to_process.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
    
    # Process the dates
    total_videos = 0
    print(f"\n📹 Processing {len(dates_to_process)} days...")
    
    for date_str in dates_to_process:
        print(f"\n📅 Processing {date_str}...")
        videos = process_videos_for_date(date_str, supabase, video_processor)
        total_videos += videos
        
        # Progress
        print(f"Progress: {dates_to_process.index(date_str)+1}/{len(dates_to_process)} days, {total_videos} videos total")
    
    # Summary
    print("\n" + "=" * 50)
    print("✅ Processing Complete!")
    print(f"   - Days processed: {len(dates_to_process)}")
    print(f"   - Total videos: {total_videos}")
    if total_videos > 0:
        print(f"   - Average per day: {total_videos/len(dates_to_process):.1f}")

if __name__ == "__main__":
    main()