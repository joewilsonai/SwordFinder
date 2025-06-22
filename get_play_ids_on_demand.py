#!/usr/bin/env python3
"""
Get play IDs on demand - only for the specific pitches you want videos for

Updated: Fixed download_video function to properly extract MP4 URLs from Baseball Savant pages
"""

import requests
import pandas as pd
from datetime import datetime
import re

def get_play_id_for_pitch(game_pk, pitcher_id, batter_id, inning, inning_topbot):
    """
    Get the play ID for a specific pitch
    Returns the LAST play ID for that at-bat (for result pitches)
    """
    url = f"https://statsapi.mlb.com/api/v1.1/game/{int(game_pk)}/feed/live"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        game_data = response.json()
        
        # Find matching at-bat
        for play in game_data.get('liveData', {}).get('plays', {}).get('allPlays', []):
            about = play.get('about', {})
            matchup = play.get('matchup', {})
            
            if (matchup.get('pitcher', {}).get('id') == pitcher_id and
                matchup.get('batter', {}).get('id') == batter_id and
                about.get('inning') == inning and
                about.get('halfInning', '').lower() == inning_topbot.lower()):
                
                # Get the LAST play ID (for final pitch)
                for event in reversed(play.get('playEvents', [])):
                    if 'playId' in event:
                        return event['playId']
        
        return None
    except:
        return None

def get_play_ids_for_pitches(pitches_df):
    """
    Get play IDs for a dataframe of pitches
    Adds 'mlb_play_id' column to the dataframe
    """
    print(f"🎯 Getting play IDs for {len(pitches_df)} pitches...")
    
    pitches_df = pitches_df.copy()
    pitches_df['mlb_play_id'] = None
    
    # Get unique games to minimize API calls
    unique_games = {}
    for idx, row in pitches_df.iterrows():
        game_key = (row['game_pk'], row['pitcher'], row['batter'], row['inning'], row['inning_topbot'])
        if game_key not in unique_games:
            unique_games[game_key] = []
        unique_games[game_key].append(idx)
    
    print(f"📊 Need to check {len(unique_games)} unique at-bats...")
    
    # Get play IDs
    found_count = 0
    for (game_pk, pitcher, batter, inning, topbot), indices in unique_games.items():
        play_id = get_play_id_for_pitch(game_pk, pitcher, batter, inning, topbot)
        
        if play_id:
            for idx in indices:
                pitches_df.at[idx, 'mlb_play_id'] = play_id
            found_count += 1
    
    print(f"✅ Found play IDs for {found_count}/{len(unique_games)} at-bats")
    
    return pitches_df

def download_video(play_id, output_file=None):
    """Download video for a play ID - now with proper video extraction!"""
    if not output_file:
        output_file = f"video_{play_id}.mp4"
    
    # First, get the Baseball Savant page
    page_url = f"https://baseballsavant.mlb.com/sporty-videos?playId={play_id}"
    
    try:
        # Get the page HTML
        response = requests.get(page_url, timeout=30)
        response.raise_for_status()
        
        # Extract the actual video URL from the HTML
        html_content = response.text
        
        # Look for video URL patterns in the HTML
        # Pattern 1: Direct MP4 URL in video tag
        video_pattern = r'src="(https://[^"]*\.mp4[^"]*)"'
        match = re.search(video_pattern, html_content)
        
        if not match:
            # Pattern 2: Look for sporty-clips URL
            video_pattern = r'(https://sporty-clips\.mlb\.com/[^"\'\\s]+\.mp4)'
            match = re.search(video_pattern, html_content)
        
        if not match:
            # Pattern 3: Any MLB video URL
            video_pattern = r'(https://[^"\'\\s]*mlb[^"\'\\s]*\.mp4[^"\'\\s]*)'
            match = re.search(video_pattern, html_content)
        
        if match:
            video_url = match.group(1)
            print(f"📹 Found video URL: {video_url[:50]}...")
            
            # Download the actual video
            video_response = requests.get(video_url, timeout=60)
            video_response.raise_for_status()
            
            with open(output_file, 'wb') as f:
                f.write(video_response.content)
            
            file_size_mb = len(video_response.content) / (1024 * 1024)
            print(f"✅ Downloaded: {output_file} ({file_size_mb:.1f} MB)")
            return True
        else:
            print(f"❌ No video URL found in page for play ID: {play_id}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to download video for play ID {play_id}: {e}")
        return False

# Example usage
if __name__ == "__main__":
    print("📚 Example: Get videos for longest home runs")
    print("=" * 60)
    
    # Load your data
    print("\n1️⃣ First, load your data:")
    print("   df = pd.read_csv('mlb_2025_full_season.csv')")
    
    print("\n2️⃣ Query for what you want:")
    print("   longest_hrs = df[df['is_home_run']].nlargest(5, 'hit_distance_sc')")
    
    print("\n3️⃣ Get play IDs for just those pitches:")
    print("   longest_hrs = get_play_ids_for_pitches(longest_hrs)")
    
    print("\n4️⃣ Download videos:")
    print("   for idx, hr in longest_hrs.iterrows():")
    print("       if hr['mlb_play_id']:")
    print("           download_video(hr['mlb_play_id'], f\"{hr['player_name']}_{hr['hit_distance_sc']}ft.mp4\")")
    
    print("\n💡 Other examples:")
    print("   - Fastest pitches: df.nlargest(10, 'release_speed')")
    print("   - Worst sword swings: df[(df['is_sword_candidate']) & (df['bat_speed'] < 50)]")
    print("   - Walk-off hits: df[(df['events'].isin(['single', 'double', 'triple', 'home_run'])) & (df['inning'] >= 9)]") 