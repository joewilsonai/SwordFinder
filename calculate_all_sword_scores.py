#!/usr/bin/env python3
"""
Calculate sword scores for all swinging strikes in the database
"""

import argparse
import os
import pandas as pd
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv
import logging
from env_config import get_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

def calculate_sword_score(row):
    """Calculate sword score based on multiple factors"""
    
    # Skip if no bat speed
    if pd.isna(row['bat_speed']) or row['bat_speed'] <= 0:
        return None
    
    # Base criteria - must be swinging strike
    if row['description'] not in ['swinging_strike', 'swinging_strike_blocked']:
        return None
    
    score = 0
    
    # 1. Bat speed component (slower = worse) - 50 points max
    if row['bat_speed'] < 60:
        speed_score = (60 - row['bat_speed']) * (50 / 60)
        score += min(speed_score, 50)
    
    # 2. Swing path tilt (worse angle = higher score) - 20 points max
    if not pd.isna(row.get('swing_path_tilt', None)):
        if row['swing_path_tilt'] > 30:
            tilt_score = (row['swing_path_tilt'] - 30) * (20 / 30)
            score += min(tilt_score, 20)
    
    # 3. Swing length (longer = worse timing) - 20 points max
    if not pd.isna(row.get('swing_length', None)):
        if row['swing_length'] > 7.5:
            length_score = (row['swing_length'] - 7.5) * (20 / 2.5)
            score += min(length_score, 20)
    
    # 4. Zone location (farther from center = worse) - 10 points max
    plate_x = row.get('plate_x', 0)
    plate_z = row.get('plate_z', 2.5)
    distance_from_center = ((plate_x ** 2) + ((plate_z - 2.5) ** 2)) ** 0.5
    if distance_from_center > 1:
        zone_score = (distance_from_center - 1) * 10
        score += min(zone_score, 10)
    
    return score if score > 0 else None

def process_batch(supabase, limit=1000, year=None, last_id=None):
    """Process one batch of unscored swinging strikes."""
    
    # Get swinging strikes without sword scores
    query = supabase.table('mlb_pitches_enhanced')\
        .select('*')\
        .in_('description', ['swinging_strike', 'swinging_strike_blocked'])\
        .is_('sword_score', 'null')\
        .order('id')\
        .range(0, limit - 1)

    if year is not None:
        query = query.gte('game_date', f'{year}-01-01').lt('game_date', f'{year + 1}-01-01')
    if last_id is not None:
        query = query.gt('id', last_id)

    result = query.execute()
    
    if not result.data:
        return 0, 0, last_id
    
    df = pd.DataFrame(result.data)
    logger.info(f"Processing batch: {len(df)} records")
    
    # Calculate scores
    updates = []
    for _, row in df.iterrows():
        score = calculate_sword_score(row)
        if score is not None:
            updates.append({
                'id': row['id'],
                'sword_score': round(score, 2)
            })
    
    # Batch update in one request for performance.
    if updates:
        supabase.table('mlb_pitches_enhanced').upsert(updates).execute()
        logger.info(f"Updated {len(updates)} records with sword scores")
    
    return len(df), len(updates), int(df['id'].max())

def parse_args():
    parser = argparse.ArgumentParser(description="Calculate sword scores in Supabase.")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Optional season year filter (example: 2026).",
    )
    return parser.parse_args()


def main():
    """Calculate sword scores for the entire database or one year."""
    args = parse_args()
    load_dotenv()
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    print("🗡️ Calculating Sword Scores for Entire Database")
    print("=" * 50)
    if args.year is not None:
        print(f"🎯 Year filter enabled: {args.year}")
    
    # Get total count of swinging strikes without scores
    count_query = supabase.table('mlb_pitches_enhanced')\
        .select('id', count='exact')\
        .in_('description', ['swinging_strike', 'swinging_strike_blocked'])\
        .is_('sword_score', 'null')

    if args.year is not None:
        count_query = count_query.gte('game_date', f'{args.year}-01-01').lt('game_date', f'{args.year + 1}-01-01')

    count_result = count_query.execute()
    
    total_to_process = count_result.count
    print(f"\n📊 Found {total_to_process:,} swinging strikes to process")
    
    if total_to_process == 0:
        print("✅ All sword scores already calculated!")
        return
    
    # Process in ID order so rows with null scores that remain null do not
    # cause us to refetch the same page repeatedly.
    batch_size = 1000
    last_id = None
    total_processed = 0
    total_updated = 0

    while True:
        processed, updated, max_id = process_batch(
            supabase,
            batch_size,
            year=args.year,
            last_id=last_id,
        )
        if processed == 0:
            break
        
        total_processed += processed
        total_updated += updated
        last_id = max_id

        # Progress
        pct = (total_processed / total_to_process) * 100
        print(
            f"Progress: {total_processed:,}/{total_to_process:,} ({pct:.1f}%) | "
            f"updated {total_updated:,}"
        )
    
    # Summary stats
    print("\n" + "=" * 50)
    print("✅ Processing Complete!")
    
    # Get final stats
    stats_query = supabase.table('mlb_pitches_enhanced')\
        .select('sword_score')\
        .not_.is_('sword_score', 'null')

    if args.year is not None:
        stats_query = stats_query.gte('game_date', f'{args.year}-01-01').lt('game_date', f'{args.year + 1}-01-01')

    stats_result = stats_query.execute()
    
    if stats_result.data:
        scores = [r['sword_score'] for r in stats_result.data]
        print(f"\n📊 Final Statistics:")
        print(f"   Total sword swings: {len(scores):,}")
        print(f"   Average score: {sum(scores)/len(scores):.1f}")
        print(f"   Max score: {max(scores):.1f}")
        print(f"   Min score: {min(scores):.1f}")
        
        # Top swords
        top_query = supabase.table('mlb_pitches_enhanced')\
            .select('player_name, sword_score, bat_speed, game_date')\
            .not_.is_('sword_score', 'null')\
            .order('sword_score', desc=True)\
            .limit(5)

        if args.year is not None:
            top_query = top_query.gte('game_date', f'{args.year}-01-01').lt('game_date', f'{args.year + 1}-01-01')

        top_result = top_query.execute()
        
        if top_result.data:
            print(f"\n🏆 Top 5 Sword Swings:")
            for i, swing in enumerate(top_result.data):
                print(f"   {i+1}. {swing['player_name']} - {swing['sword_score']:.1f} ({swing['bat_speed']} mph) on {swing['game_date']}")

if __name__ == "__main__":
    main() 
