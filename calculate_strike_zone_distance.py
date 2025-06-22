#!/usr/bin/env python3
"""
Calculate distance from strike zone for all pitches
Adds new field: strike_zone_distance_inches
"""

import os
import pandas as pd
import numpy as np
from supabase import create_client
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def calculate_strike_zone_distance(plate_x, plate_z, sz_top, sz_bot):
    """
    Calculate minimum distance from the strike zone edge in inches
    
    Strike zone:
    - Width: 17 inches (plate width) = 1.417 feet
    - Half width: 8.5 inches = 0.708 feet
    - Height: sz_top to sz_bot (varies by batter)
    
    Returns distance in inches from nearest edge of zone
    """
    if pd.isna(plate_x) or pd.isna(plate_z) or pd.isna(sz_top) or pd.isna(sz_bot):
        return None
    
    # Strike zone boundaries
    HALF_PLATE_WIDTH = 8.5 / 12  # 0.708 feet
    
    # Calculate horizontal distance from zone
    horizontal_distance_feet = max(0, abs(plate_x) - HALF_PLATE_WIDTH)
    
    # Calculate vertical distance from zone
    if plate_z > sz_top:
        vertical_distance_feet = plate_z - sz_top
    elif plate_z < sz_bot:
        vertical_distance_feet = sz_bot - plate_z
    else:
        vertical_distance_feet = 0
    
    # If inside both horizontal and vertical bounds, distance is 0
    if horizontal_distance_feet == 0 and vertical_distance_feet == 0:
        return 0.0
    
    # Calculate Euclidean distance to nearest edge
    distance_feet = np.sqrt(horizontal_distance_feet**2 + vertical_distance_feet**2)
    
    # Convert to inches
    distance_inches = distance_feet * 12
    
    return round(distance_inches, 1)

def add_strike_zone_distance_column():
    """Add strike zone distance column to database if it doesn't exist"""
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    supabase = create_client(supabase_url, supabase_key)
    
    # Add column
    sql = """
    ALTER TABLE mlb_pitches_enhanced 
    ADD COLUMN IF NOT EXISTS strike_zone_distance_inches REAL;
    """
    
    print("⚠️  To add strike zone distance column, run this SQL in Supabase:")
    print(sql)
    
    return supabase

def process_batch(supabase, offset, batch_size=1000):
    """Process a batch of pitches to calculate strike zone distance"""
    
    # Get batch
    result = supabase.table('mlb_pitches_enhanced')\
        .select('id, plate_x, plate_z, sz_top, sz_bot')\
        .not_.is_('plate_x', 'null')\
        .not_.is_('plate_z', 'null')\
        .range(offset, offset + batch_size - 1)\
        .execute()
    
    if not result.data:
        return 0
    
    df = pd.DataFrame(result.data)
    logger.info(f"Processing batch: {len(df)} records from offset {offset}")
    
    # Calculate strike zone distance
    df['strike_zone_distance_inches'] = df.apply(
        lambda row: calculate_strike_zone_distance(
            row['plate_x'], row['plate_z'], row['sz_top'], row['sz_bot']
        ), 
        axis=1
    )
    
    # Update database
    updates = 0
    for _, row in df.iterrows():
        if pd.notna(row['strike_zone_distance_inches']):
            supabase.table('mlb_pitches_enhanced')\
                .update({'strike_zone_distance_inches': row['strike_zone_distance_inches']})\
                .eq('id', row['id'])\
                .execute()
            updates += 1
    
    return updates

def main():
    """Calculate strike zone distance for all pitches"""
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    print("📏 Strike Zone Distance Calculator")
    print("=" * 50)
    
    # Show column creation SQL
    add_strike_zone_distance_column()
    
    # Get count of pitches to process
    count_result = supabase.table('mlb_pitches_enhanced')\
        .select('id', count='exact')\
        .not_.is_('plate_x', 'null')\
        .not_.is_('plate_z', 'null')\
        .is_('strike_zone_distance_inches', 'null')\
        .execute()
    
    total_to_process = count_result.count
    print(f"\n📊 Found {total_to_process:,} pitches to process")
    
    if total_to_process == 0:
        print("✅ All strike zone distances already calculated!")
        
        # Show worst sword swings by distance
        worst_swords = supabase.table('mlb_pitches_enhanced')\
            .select('player_name, pitcher_name, bat_speed, sword_score, strike_zone_distance_inches, description')\
            .gt('sword_score', 80)\
            .gt('strike_zone_distance_inches', 0)\
            .order('strike_zone_distance_inches', desc=True)\
            .limit(10)\
            .execute()
        
        if worst_swords.data:
            print("\n🎯 Worst Sword Swings by Distance from Zone:")
            print(f"{'Player':20} {'Pitcher':20} {'Bat Speed':>10} {'Distance':>10} {'Description':20}")
            print("-" * 85)
            for swing in worst_swords.data:
                print(f"{swing['player_name'][:20]:20} {swing['pitcher_name'][:20]:20} "
                      f"{swing['bat_speed']:>10.1f} {swing['strike_zone_distance_inches']:>10.1f}\" "
                      f"{swing['description'][:20]:20}")
        
        return
    
    # Process in batches
    batch_size = 1000
    offset = 0
    total_updated = 0
    
    while offset < total_to_process:
        updated = process_batch(supabase, offset, batch_size)
        total_updated += updated
        offset += batch_size
        
        if total_updated % 10000 == 0:
            print(f"Progress: {total_updated:,}/{total_to_process:,} ({total_updated/total_to_process*100:.1f}%)")
    
    print(f"\n✅ Complete! Calculated {total_updated:,} strike zone distances")
    
    # Show some interesting stats
    print("\n📊 Strike Zone Distance Stats for Sword Swings:")
    
    stats_sql = """
    SELECT 
        AVG(strike_zone_distance_inches) as avg_distance,
        MAX(strike_zone_distance_inches) as max_distance,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY strike_zone_distance_inches) as median_distance,
        COUNT(*) as total_swords
    FROM mlb_pitches_enhanced
    WHERE sword_score > 0 AND strike_zone_distance_inches IS NOT NULL
    """
    
    print("\nSQL to run for stats:")
    print(stats_sql)

if __name__ == "__main__":
    main() 