#!/usr/bin/env python3
"""
Get top N sword swing videos, skipping any without play IDs
Guarantees you get exactly N videos (or all available if fewer exist)
"""

import os
import pandas as pd
from get_play_ids_on_demand import get_play_ids_for_pitches
from clean_video_processor import EnhancedSwordVideoProcessor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_top_n_sword_videos(date_str, n_videos=5, max_attempts=20):
    """
    Get exactly n_videos sword swings, skipping any without play IDs
    
    Args:
        date_str: Date to get videos for (YYYY-MM-DD)
        n_videos: Number of videos to download
        max_attempts: Maximum sword swings to check before giving up
    
    Returns:
        Number of videos successfully downloaded
    """
    print(f"🗡️ Getting Top {n_videos} Sword Videos for {date_str}")
    print("=" * 60)
    
    # Load the CSV with sword scores
    print("📊 Loading data with sword scores...")
    df = pd.read_csv('mlb_2025_with_sword_scores.csv', low_memory=False)
    df['game_date'] = pd.to_datetime(df['game_date'])
    
    # Get all sword candidates for the date, sorted by score
    date_swords = df[
        (df['game_date'] == date_str) & 
        (df['sword_score'].notna())
    ].sort_values('sword_score', ascending=False)
    
    if date_swords.empty:
        print(f"❌ No sword swings found for {date_str}")
        return 0
    
    print(f"📊 Found {len(date_swords)} total sword swings for {date_str}")
    
    # Create videos directory
    video_dir = f'sword_videos_{date_str.replace("-", "")}_guaranteed'
    os.makedirs(video_dir, exist_ok=True)
    
    # Initialize video processor
    video_processor = EnhancedSwordVideoProcessor()
    
    # Process in batches to find videos
    downloaded_count = 0
    checked_count = 0
    batch_size = 5
    
    print(f"\n🎯 Goal: Download {n_videos} videos (checking up to {max_attempts} swings)")
    print("-" * 60)
    
    while downloaded_count < n_videos and checked_count < min(len(date_swords), max_attempts):
        # Get next batch
        batch_start = checked_count
        batch_end = min(checked_count + batch_size, len(date_swords))
        batch = date_swords.iloc[batch_start:batch_end]
        
        if batch.empty:
            break
        
        print(f"\n📡 Checking batch {batch_start+1}-{batch_end} for play IDs...")
        
        # Get play IDs for batch
        batch_with_ids = get_play_ids_for_pitches(batch)
        
        # Try to download videos from this batch
        for i in range(len(batch_with_ids)):
            if downloaded_count >= n_videos:
                break
                
            pitch = batch_with_ids.iloc[i]
            rank = checked_count + i + 1
            
            print(f"\n{rank}. {pitch['player_name']} - Score: {pitch['sword_score']:.1f} ({pitch['bat_speed']:.1f} mph)")
            
            if pd.notna(pitch.get('mlb_play_id', None)):
                player_name_safe = str(pitch['player_name']).replace(' ', '_')
                filename = f"{video_dir}/{downloaded_count+1}_{player_name_safe}_score{pitch['sword_score']:.0f}_rank{rank}.mp4"
                
                # Get video URL
                video_url = video_processor.get_video_url_for_play(
                    str(pitch.get('game_pk', '')), 
                    pitch['mlb_play_id']
                )
                
                if video_url:
                    # Download the video
                    success = video_processor.download_video_locally(video_url, filename)
                    if success:
                        downloaded_count += 1
                        print(f"   ✅ Downloaded #{downloaded_count}: {filename}")
                    else:
                        print(f"   ❌ Failed to download video")
                else:
                    print(f"   ❌ No video URL found")
            else:
                print(f"   ⚠️  No play ID - skipping to next")
        
        checked_count = batch_end
        
        # Status update
        if downloaded_count < n_videos:
            print(f"\n📊 Progress: {downloaded_count}/{n_videos} videos downloaded, {checked_count} swings checked")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"📊 Final Summary for {date_str}:")
    print(f"   - Total sword swings: {len(date_swords)}")
    print(f"   - Swings checked: {checked_count}")
    print(f"   - Videos downloaded: {downloaded_count}")
    print(f"   - Videos saved to: {video_dir}/")
    
    if downloaded_count == n_videos:
        print(f"\n✅ Success! Got all {n_videos} requested videos!")
    elif downloaded_count > 0:
        print(f"\n⚠️  Only found {downloaded_count} videos out of {n_videos} requested")
    else:
        print(f"\n❌ No videos could be downloaded")
    
    return downloaded_count

def main():
    """Example usage"""
    import sys
    
    # Default values
    date = '2025-06-20'
    n_videos = 5
    
    # Parse command line args
    if len(sys.argv) > 1:
        date = sys.argv[1]
    if len(sys.argv) > 2:
        n_videos = int(sys.argv[2])
    
    # Get the videos
    get_top_n_sword_videos(date, n_videos)

if __name__ == "__main__":
    main() 