#!/usr/bin/env python3
"""
Download FULL 2025 MLB Season Data
All 123 fields, ready for instant querying
"""

import pybaseball
import pandas as pd
from datetime import datetime
import os

def download_full_2025_season():
    """Download complete 2025 season data"""
    
    print("⚾ FULL 2025 MLB SEASON DOWNLOAD")
    print("=" * 60)
    
    # Season dates
    start_date = '2025-03-20'  # Opening day
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    output_file = 'mlb_2025_full_season_complete.csv'
    
    print(f"📅 Season: {start_date} to {end_date}")
    print("\n⏱️ This will take about 2-3 minutes...")
    print("   (Downloading ~200,000+ pitches with 123 fields each)")
    
    # Download everything
    print("\n📥 Downloading from MLB Statcast...")
    df = pybaseball.statcast(start_dt=start_date, end_dt=end_date)
    
    print(f"\n✅ Downloaded {len(df):,} pitches!")
    print(f"📊 Data has {len(df.columns)} columns")
    
    # Add useful flags
    print("\n🏷️ Adding query helper flags...")
    
    # Event flags
    df['is_home_run'] = df['events'] == 'home_run'
    df['is_strikeout'] = df['events'] == 'strikeout'
    df['is_walk'] = df['events'].isin(['walk', 'intent_walk'])
    df['is_hit'] = df['events'].isin(['single', 'double', 'triple', 'home_run'])
    df['is_extra_base_hit'] = df['events'].isin(['double', 'triple', 'home_run'])
    
    # Swing and miss
    df['is_whiff'] = df['description'].isin(['swinging_strike', 'swinging_strike_blocked'])
    
    # Sword candidates (2-strike swinging strikeouts)
    df['is_sword_candidate'] = (
        (df['strikes'] == 2) & 
        (df['events'] == 'strikeout') &
        df['is_whiff']
    )
    
    # True sword swings (with bat tracking)
    df['is_true_sword'] = (
        df['is_sword_candidate'] & 
        (df['bat_speed'] < 60) & 
        (df['swing_path_tilt'] > 30)
    )
    
    # High velo
    df['is_100_plus'] = df['release_speed'] >= 100
    
    # Save
    print(f"\n💾 Saving to {output_file}...")
    df.to_csv(output_file, index=False)
    
    file_size = os.path.getsize(output_file) / (1024*1024)
    
    # Summary stats
    print("\n📊 SEASON SUMMARY:")
    print(f"   Total pitches: {len(df):,}")
    print(f"   Unique games: {df['game_pk'].nunique():,}")
    print(f"   Home runs: {df['is_home_run'].sum():,}")
    print(f"   Strikeouts: {df['is_strikeout'].sum():,}")
    print(f"   100+ mph pitches: {df['is_100_plus'].sum():,}")
    
    if df['bat_speed'].notna().sum() > 0:
        print(f"\n🏏 BAT TRACKING STATS:")
        print(f"   Swings tracked: {df['bat_speed'].notna().sum():,}")
        print(f"   Avg bat speed: {df['bat_speed'].mean():.1f} mph")
        print(f"   Sword candidates: {df['is_sword_candidate'].sum():,}")
        print(f"   True sword swings: {df['is_true_sword'].sum():,}")
    
    print(f"\n📁 File size: {file_size:.1f} MB")
    print(f"✅ Saved to: {output_file}")
    
    print("\n🎯 READY TO QUERY!")
    print("Examples:")
    print("   df = pd.read_csv('mlb_2025_full_season_complete.csv')")
    print("   ")
    print("   # Longest homers by month")
    print("   df[df['is_home_run']].groupby(pd.to_datetime(df['game_date']).dt.month).apply(")
    print("       lambda x: x.nlargest(5, 'hit_distance_sc'))")
    print("   ")
    print("   # Worst sword swings by team")  
    print("   df[df['is_true_sword']].groupby('home_team').apply(")
    print("       lambda x: x.nsmallest(3, 'bat_speed'))")
    print("   ")
    print("   # Then just get play IDs and download videos!")
    
    return df

if __name__ == "__main__":
    df = download_full_2025_season() 