#!/usr/bin/env python3
"""
Calculate perceived velocity based on release extension
Perceived velocity accounts for how extension affects the time a batter has to react
"""

import os
import pandas as pd
import numpy as np
from supabase import create_client
from dotenv import load_dotenv
import logging
from env_config import get_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_perceived_velocity(actual_velocity, extension):
    """
    Calculate perceived velocity based on extension
    
    Formula: perceived_velocity = actual_velocity * (distance / (distance - extension))
    Where distance = 60.5 feet (60 feet 6 inches)
    
    Example: 95 mph with 7 feet extension
    = 95 * (60.5 / (60.5 - 7))
    = 95 * (60.5 / 53.5)
    = 95 * 1.131
    = 107.4 mph perceived
    """
    if pd.isna(actual_velocity) or pd.isna(extension):
        return None
    
    # Standard distance from rubber to plate in feet
    MOUND_DISTANCE = 60.5
    
    # Calculate effective distance
    effective_distance = MOUND_DISTANCE - extension
    
    # Avoid division by zero
    if effective_distance <= 0:
        return None
    
    # Calculate perceived velocity
    perceived = actual_velocity * (MOUND_DISTANCE / effective_distance)
    
    return round(perceived, 1)

def add_perceived_velocity_column():
    """Add perceived velocity column to database if it doesn't exist"""
    load_dotenv()
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')
    supabase = create_client(supabase_url, supabase_key)
    
    # Add column
    sql = """
    ALTER TABLE mlb_pitches_enhanced 
    ADD COLUMN IF NOT EXISTS perceived_velocity REAL,
    ADD COLUMN IF NOT EXISTS perceived_velo_percentile_overall REAL,
    ADD COLUMN IF NOT EXISTS perceived_velo_percentile_pitch_type REAL;
    """
    
    try:
        supabase.rpc('execute_sql', {'query': sql}).execute()
        logger.info("Added perceived velocity columns")
    except Exception:
        logger.info("Columns may already exist")

def process_perceived_velocity_batch(supabase, offset, batch_size=1000):
    """Process a batch of pitches to calculate perceived velocity"""
    
    # Get batch
    result = supabase.table('mlb_pitches_enhanced')\
        .select('id, release_speed, release_extension')\
        .not_.is_('release_speed', 'null')\
        .not_.is_('release_extension', 'null')\
        .range(offset, offset + batch_size - 1)\
        .execute()
    
    if not result.data:
        return 0
    
    df = pd.DataFrame(result.data)
    logger.info(f"Processing batch: {len(df)} records from offset {offset}")
    
    # Calculate perceived velocity
    df['perceived_velocity'] = df.apply(
        lambda row: calculate_perceived_velocity(row['release_speed'], row['release_extension']), 
        axis=1
    )
    
    # Update database
    updates = 0
    for _, row in df.iterrows():
        if pd.notna(row['perceived_velocity']):
            supabase.table('mlb_pitches_enhanced')\
                .update({'perceived_velocity': row['perceived_velocity']})\
                .eq('id', int(row['id']))\
                .execute()
            updates += 1
    
    return updates

def main():
    """Calculate perceived velocity for all pitches"""
    load_dotenv()
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    print("⚡ Perceived Velocity Calculator")
    print("=" * 50)
    
    # Add columns if needed
    add_perceived_velocity_column()
    
    # Get count of pitches to process
    count_result = supabase.table('mlb_pitches_enhanced')\
        .select('id', count='exact')\
        .not_.is_('release_speed', 'null')\
        .not_.is_('release_extension', 'null')\
        .is_('perceived_velocity', 'null')\
        .execute()
    
    total_to_process = count_result.count
    print(f"\n📊 Found {total_to_process:,} pitches to process")
    
    if total_to_process == 0:
        print("✅ All perceived velocities already calculated!")
        
        # Show some stats
        stats = supabase.table('mlb_pitches_enhanced')\
            .select('pitcher_name, release_speed, release_extension, perceived_velocity')\
            .gt('perceived_velocity', 100)\
            .order('perceived_velocity', desc=True)\
            .limit(10)\
            .execute()
        
        if stats.data:
            print("\n🔥 Highest Perceived Velocities:")
            for pitch in stats.data:
                ext = pitch['release_extension']
                actual = pitch['release_speed']
                perceived = pitch['perceived_velocity']
                gain = perceived - actual
                print(f"   {pitch['pitcher_name']}: {perceived:.1f} mph perceived ({actual:.1f} actual, {ext:.1f}' extension, +{gain:.1f} mph)")
        
        return
    
    # Process in batches
    batch_size = 1000
    offset = 0
    total_updated = 0
    
    while offset < total_to_process:
        updated = process_perceived_velocity_batch(supabase, offset, batch_size)
        total_updated += updated
        offset += batch_size
        
        if total_updated % 10000 == 0:
            print(f"Progress: {total_updated:,}/{total_to_process:,} ({total_updated/total_to_process*100:.1f}%)")
    
    print(f"\n✅ Complete! Calculated {total_updated:,} perceived velocities")
    
    # Show extremes
    print("\n📊 Extension and Perceived Velocity Stats:")
    
    # Best extensions
    best_ext = supabase.table('mlb_pitches_enhanced')\
        .select('pitcher_name, pitch_type, release_extension, release_speed, perceived_velocity')\
        .gt('release_extension', 7.5)\
        .order('release_extension', desc=True)\
        .limit(5)\
        .execute()
    
    if best_ext.data:
        print("\n🏃 Longest Extensions:")
        for pitch in best_ext.data:
            print(f"   {pitch['pitcher_name']}: {pitch['release_extension']:.1f}' on {pitch['pitch_type']} ({pitch['perceived_velocity']:.1f} perceived)")
    
    # Biggest perceived velocity gains
    print("\n📈 SQL to find biggest perceived velocity gains:")
    print("""
    SELECT pitcher_name, pitch_type, 
           release_speed, release_extension, perceived_velocity,
           (perceived_velocity - release_speed) as velocity_gain
    FROM mlb_pitches_enhanced
    WHERE perceived_velocity IS NOT NULL
    ORDER BY velocity_gain DESC
    LIMIT 10;
    """)

if __name__ == "__main__":
    main() 
