#!/usr/bin/env python3
"""
Process videos for yesterday's top sword swings
Runs after the daily data update to download and upload videos
"""

import os
import sys
from datetime import datetime, timedelta
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
import logging
from get_play_ids_on_demand import get_play_ids_for_pitches
from clean_video_processor import MLBVideoProcessor

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_processing.log'),
        logging.StreamHandler()
    ]
)

def get_yesterdays_top_swords(supabase, date_str: str, top_n: int = 10):
    """Get yesterday's top sword swings from the database"""
    
    # Query for yesterday's sword candidates
    result = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .eq('game_date', date_str)\
        .not_.is_('sword_score', 'null')\
        .gt('sword_score', 0)\
        .is_('video_azure_blob_url', 'null')\
        .order('sword_score', desc=True)\
        .limit(top_n * 2)\
        .execute()
    
    if not result.data:
        logging.warning(f"No sword candidates found for {date_str}")
        return pd.DataFrame()
    
    df = pd.DataFrame(result.data)
    logging.info(f"Found {len(df)} sword candidates for {date_str}")
    
    # Take top N by sword score
    top_swords = df.nlargest(min(top_n, len(df)), 'sword_score')
    
    return top_swords

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
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
    
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
            local_path = f"temp_{video_filename}"
            
            logging.info(f"Processing video for {pitch.get('player_name')} ({bat_speed:.1f} mph)")
            
            # Download from MLB
            success = video_processor.download_video(pitch['mlb_play_id'], local_path)
            
            if success and os.path.exists(local_path):
                # Upload to Azure
                blob_name = f"swords/{date_str}/{video_filename}"
                azure_url = video_processor.upload_to_azure(local_path, blob_name)
                
                if azure_url:
                    # Update database
                    update_result = supabase.table('mlb_pitches_enhanced').update({
                        'video_azure_blob_url': azure_url,
                        'video_processed_at': datetime.now().isoformat()
                    }).eq('game_pk', pitch.get('game_pk'))\
                     .eq('at_bat_number', pitch.get('at_bat_number'))\
                     .eq('pitch_number', pitch.get('pitch_number'))\
                     .execute()
                    
                    processed_count += 1
                    logging.info(f"✅ Video uploaded: {azure_url}")
                
                # Clean up
                if os.path.exists(local_path):
                    os.remove(local_path)
            else:
                logging.warning(f"Failed to download video for play {pitch['mlb_play_id']}")
                
        except Exception as e:
            logging.error(f"Error processing video: {e}")
    
    return processed_count

def main():
    """Main execution"""
    logging.info("Starting daily sword video processing...")
    
    # Get yesterday's date
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    logging.info(f"Processing videos for {date_str}")
    
    # Load environment
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
    
    if not supabase_url or not supabase_key:
        logging.error("Missing Supabase credentials")
        sys.exit(1)
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Get top swords
    top_swords = get_yesterdays_top_swords(supabase, date_str, top_n=10)
    
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