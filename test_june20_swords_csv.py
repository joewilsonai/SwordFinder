#!/usr/bin/env python3
"""
Test script to find top 5 sword swings for June 20, 2025 using CSV data
"""

import os
import pandas as pd
from get_play_ids_on_demand import get_play_ids_for_pitches
from clean_video_processor import EnhancedSwordVideoProcessor
from datetime import datetime

def get_top_swords_from_csv(date_str):
    """Get top 5 sword swings for a specific date from CSV"""
    
    print(f"🔍 Loading CSV data...")
    
    # Load the CSV file
    try:
        df = pd.read_csv('mlb_2025_full_season_complete.csv')
        print(f"✅ Loaded {len(df)} total pitches")
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return None
    
    # Convert date column
    df['game_date'] = pd.to_datetime(df['game_date'])
    
    # Filter for the specific date and sword criteria
    print(f"🔍 Searching for sword swings on {date_str}...")
    
    sword_df = df[
        (df['game_date'] == date_str) &
        (df['description'] == 'swinging_strike') &
        (df['strikes'] == 2) &
        (df['bat_speed'] < 60) &
        (df['bat_speed'] > 0)
    ].copy()
    
    if sword_df.empty:
        print(f"❌ No sword swings found for {date_str}")
        # Check what data we have for that date
        date_df = df[df['game_date'] == date_str]
        print(f"   Total pitches on {date_str}: {len(date_df)}")
        
        # Check for swinging strikes on that date
        swinging_strikes = date_df[date_df['description'] == 'swinging_strike']
        print(f"   Swinging strikes: {len(swinging_strikes)}")
        
        # Check for slow bat speeds
        slow_swings = date_df[(date_df['bat_speed'] < 60) & (date_df['bat_speed'] > 0)]
        print(f"   Slow swings (< 60 mph): {len(slow_swings)}")
        
        return None
    
    # Sort by bat speed (slowest first) and take top 5
    sword_df = sword_df.sort_values('bat_speed').head(5)
    
    print(f"✅ Found {len(sword_df)} sword candidates!")
    return sword_df

def main():
    # Test date
    test_date = '2025-06-20'
    
    print(f"🎯 SwordFinder Video Test - {test_date}")
    print("=" * 50)
    
    # Get top swords from CSV
    df = get_top_swords_from_csv(test_date)
    
    if df is None or df.empty:
        print("\n❌ No sword swings found. Checking available dates...")
        
        # Load CSV to check dates
        try:
            full_df = pd.read_csv('mlb_2025_full_season_complete.csv')
            full_df['game_date'] = pd.to_datetime(full_df['game_date'])
            
            # Get unique dates sorted
            dates = full_df['game_date'].dt.date.unique()
            dates = sorted(dates, reverse=True)
            
            print(f"\nTotal dates in database: {len(dates)}")
            print("Most recent dates:")
            for date in dates[:10]:
                print(f"  - {date}")
            
            print("\nDate range: {} to {}".format(min(dates), max(dates)))
            
            # Try June 19 or 21 instead
            for alt_date in ['2025-06-19', '2025-06-21', '2025-06-18']:
                print(f"\nTrying {alt_date}...")
                alt_df = get_top_swords_from_csv(alt_date)
                if alt_df is not None and not alt_df.empty:
                    df = alt_df
                    test_date = alt_date
                    break
                    
        except Exception as e:
            print(f"Error checking dates: {e}")
            
        if df is None:
            return
    
    # Display the sword swings
    print(f"\n🗡️ Top 5 Sword Swings for {test_date}:")
    print("-" * 80)
    for i in range(len(df)):
        row = df.iloc[i]
        print(f"{i+1}. {row['player_name']} - {row['bat_speed']:.1f} mph")
        print(f"   Pitch: {row['pitch_type']} @ {row['release_speed']:.1f} mph")
        print(f"   Game: {row['home_team']} vs {row['away_team']}")
        print(f"   Count: {row['balls']}-{row['strikes']}, Inning: {row['inning']}")
    
    # Get play IDs
    print("\n📡 Getting play IDs from MLB...")
    df_with_ids = get_play_ids_for_pitches(df)
    
    # Count successful IDs
    ids_found = df_with_ids['mlb_play_id'].notna().sum()
    print(f"✅ Found {ids_found}/{len(df)} play IDs")
    
    # Create videos directory
    video_dir = f'sword_videos_{test_date.replace("-", "")}'
    os.makedirs(video_dir, exist_ok=True)
    
    # Initialize video processor
    video_processor = EnhancedSwordVideoProcessor()
    
    # Download videos
    print("\n📹 Downloading videos...")
    successful_downloads = 0
    
    for i in range(len(df_with_ids)):
        pitch = df_with_ids.iloc[i]
        if pd.notna(pitch.get('mlb_play_id', None)):
            player_name_safe = str(pitch['player_name']).replace(' ', '_')
            filename = f"{video_dir}/{i+1}_{player_name_safe}_{pitch['bat_speed']:.0f}mph.mp4"
            print(f"\n{i+1}. Downloading: {pitch['player_name']} ({pitch['bat_speed']:.1f} mph)")
            
            # Get video URL first
            video_url = video_processor.get_video_url_for_play(
                str(pitch.get('game_pk', '')), 
                pitch['mlb_play_id']
            )
            
            if video_url:
                # Download the video
                success = video_processor.download_video_locally(video_url, filename)
                if success:
                    successful_downloads += 1
                    print(f"   ✅ Saved to: {filename}")
                else:
                    print(f"   ❌ Failed to download")
            else:
                print(f"   ❌ No video URL found")
        else:
            print(f"\n{i+1}. ⚠️  No play ID for: {pitch['player_name']}")
    
    # Summary
    print("\n" + "=" * 50)
    print(f"📊 Summary for {test_date}:")
    print(f"   - Top sword swings found: {len(df)}")
    print(f"   - Play IDs retrieved: {ids_found}")
    print(f"   - Videos downloaded: {successful_downloads}")
    print(f"   - Videos saved to: {video_dir}/")
    
    if successful_downloads > 0:
        print(f"\n✅ Success! Check the {video_dir} directory for videos.")

if __name__ == "__main__":
    main() 