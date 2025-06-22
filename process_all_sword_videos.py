#!/usr/bin/env python3
"""
Process all sword videos for the entire 2025 season
- Upload sword scores to Supabase
- Download top 5 videos per day
- Upload to Azure and update database
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv
from get_play_ids_on_demand import get_play_ids_for_pitches
from clean_video_processor import EnhancedSwordVideoProcessor
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_sword_scores_to_supabase():
    """Upload all sword scores from CSV to Supabase"""
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return False
    
    supabase = create_client(supabase_url, supabase_key)
    
    logger.info("📊 Loading CSV with sword scores...")
    df = pd.read_csv('mlb_2025_with_sword_scores.csv', low_memory=False)
    
    # Get only records with sword scores
    sword_df = df[df['sword_score'].notna()].copy()
    logger.info(f"Found {len(sword_df)} sword candidates to update")
    
    # Update in batches
    batch_size = 100
    updated = 0
    
    for i in range(0, len(sword_df), batch_size):
        batch = sword_df.iloc[i:i+batch_size]
        
        try:
            # Update each record
            for _, row in batch.iterrows():
                # Find matching record by game_pk, at_bat_number, pitch_number
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

def main():
    """Process all sword videos for the season"""
    load_dotenv()
    
    # Initialize
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    video_processor = EnhancedSwordVideoProcessor()
    
    print("🗡️ SwordFinder Season Video Processor")
    print("=" * 50)
    
    # Step 1: Upload sword scores
    print("\n📊 Step 1: Uploading sword scores to Supabase...")
    if not upload_sword_scores_to_supabase():
        print("❌ Failed to upload scores. Exiting.")
        return
    
    # Step 2: Process videos
    print("\n📹 Step 2: Processing videos for each day...")
    
    # Get date range
    start_date = datetime(2025, 3, 20)
    end_date = datetime(2025, 6, 21)
    
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
    print("✅ Season Processing Complete!")
    print(f"   - Days processed: {total_days}")
    print(f"   - Days with videos: {days_with_videos}")
    print(f"   - Total videos: {total_videos}")
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