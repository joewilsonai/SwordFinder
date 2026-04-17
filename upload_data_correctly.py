#!/usr/bin/env python3
"""
Correctly upload MLB data with proper float handling
"""

import argparse
from datetime import datetime
import pandas as pd
import os
from dotenv import load_dotenv
from supabase import create_client
from tqdm import tqdm
import numpy as np
from env_config import get_env

# Load environment variables
load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(description="Upload season CSV data to Supabase.")
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--input-file", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview only.")
    parser.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Skip interactive confirmation before full upload.",
    )
    return parser.parse_args()


def resolve_input_file(year, input_file):
    if input_file:
        return input_file
    candidate = f"mlb_{year}_full_season_complete.csv"
    if os.path.exists(candidate):
        return candidate
    if year == 2025 and os.path.exists("mlb_2025_full_season_complete.csv"):
        return "mlb_2025_full_season_complete.csv"
    raise FileNotFoundError(
        f"Could not find {candidate}. Use --input-file to specify a CSV."
    )

def clean_value(value):
    """Clean a single value for PostgreSQL/JSON"""
    # Handle None/NaN
    if pd.isna(value):
        return None
    
    # Handle infinity
    if isinstance(value, (float, np.floating)):
        if np.isinf(value):
            return None
        # Keep floats as floats
        return float(value)
    
    # Handle integers
    if isinstance(value, (int, np.integer)):
        return int(value)
    
    # Handle booleans
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    
    # Handle strings
    if isinstance(value, str):
        if value == 'nan' or value == 'None':
            return None
        return value
    
    # Default: convert to native Python type
    return value

def prepare_data(df):
    """Prepare dataframe for upload"""
    print("🔄 Preparing data with correct types...")
    
    # Define column types
    integer_columns = [
        'pitcher', 'batter', 'balls', 'strikes', 'outs_when_up', 
        'inning', 'zone', 'pitch_number', 'at_bat_number', 
        'hit_location', 'game_year'
    ]
    
    # First, select only columns that exist
    existing_columns = [col for col in df.columns if col in [
        # Core columns we need
        'game_pk', 'game_date', 'game_type', 'game_year', 'home_team', 'away_team',
        'pitch_type', 'pitch_name', 'pitch_number', 'at_bat_number',
        'pitcher', 'batter', 'player_name', 'stand', 'p_throws',
        'balls', 'strikes', 'outs_when_up', 'inning', 'inning_topbot',
        'on_1b', 'on_2b', 'on_3b',
        'release_speed', 'effective_speed', 'release_spin_rate', 'release_extension',
        'release_pos_x', 'release_pos_y', 'release_pos_z',
        'pfx_x', 'pfx_z', 'plate_x', 'plate_z',
        'events', 'description', 'hit_location', 'hit_distance_sc',
        'launch_speed', 'launch_angle', 'launch_speed_angle', 'hc_x', 'hc_y',
        'zone', 'type', 'bat_speed', 'swing_length', 'swing_path_tilt', 'attack_angle',
        'mlb_play_id', 'is_home_run', 'is_strikeout', 'is_walk', 'is_hit',
        'is_sword_candidate', 'is_true_sword'
    ]]
    
    # Create a new dataframe with only existing columns
    clean_df = df[existing_columns].copy()
    
    # Convert specific columns to correct types
    for col in integer_columns:
        if col in clean_df.columns:
            # Convert to float first to handle decimals, then to int
            clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce').fillna(0).astype('Int64')
    
    # Convert game_pk to integer
    if 'game_pk' in clean_df.columns:
        clean_df['game_pk'] = pd.to_numeric(clean_df['game_pk'], errors='coerce').fillna(0).astype('Int64')
    
    # Ensure boolean columns are bool
    bool_columns = ['on_1b', 'on_2b', 'on_3b', 'is_home_run', 'is_strikeout', 
                    'is_walk', 'is_hit', 'is_sword_candidate', 'is_true_sword']
    for col in bool_columns:
        if col in clean_df.columns:
            clean_df[col] = clean_df[col].astype(bool)
    
    # Add computed columns
    # Statcast convention: player_name = PITCHER's name. Copy to pitcher_name for UI convenience.
    clean_df['pitcher_name'] = clean_df['player_name'] if 'player_name' in clean_df.columns else None

    # batter_name is not in Statcast raw data — resolve from MLB Stats API via cached helper.
    if 'batter' in clean_df.columns:
        try:
            from resolve_player_names import resolve_names
            unique_batters = [int(x) for x in clean_df['batter'].dropna().unique()]
            name_map = resolve_names(unique_batters)
            clean_df['batter_name'] = clean_df['batter'].map(lambda b: name_map.get(int(b)) if pd.notna(b) else None)
            print(f"  resolved {len(name_map)}/{len(unique_batters)} batter names")
        except Exception as e:
            print(f"  batter_name resolution failed: {e} — column left empty")
            clean_df['batter_name'] = None

    clean_df['is_whiff'] = clean_df['description'].isin(['swinging_strike', 'swinging_strike_blocked']) if 'description' in clean_df.columns else False
    clean_df['has_bat_tracking'] = clean_df['bat_speed'].notna() if 'bat_speed' in clean_df.columns else False
    
    # Calculate sword score
    if 'bat_speed' in clean_df.columns and 'release_speed' in clean_df.columns:
        clean_df['sword_score'] = (
            (100 - clean_df['bat_speed'].fillna(100)) * 0.5 +
            (clean_df['release_speed'].fillna(90) - 80) * 0.5
        )
    
    return clean_df

def main():
    """Main upload function"""
    args = parse_args()
    print("🚀 MLB DATA UPLOAD - CORRECT VERSION")
    print("=" * 60)

    # Connect
    supabase_url = get_env("SUPABASE_URL")
    supabase_key = get_env("SUPABASE_SERVICE_ROLE_KEY") or get_env("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        print("❌ Missing credentials!")
        return

    input_file = resolve_input_file(args.year, args.input_file)
    print(f"📄 Input CSV: {input_file}")

    if args.dry_run:
        print("🧪 Dry run mode enabled (no database writes).")
        supabase = None
    else:
        print("🔌 Connecting to Supabase...")
        supabase = create_client(supabase_url, supabase_key)
        print("✅ Connected!")

    # Load data
    print("\n📊 Loading MLB data...")
    df = pd.read_csv(input_file, low_memory=False)
    print(f"✅ Loaded {len(df):,} pitches")

    # Prepare data
    clean_df = prepare_data(df)
    print(f"✅ Prepared {len(clean_df.columns)} columns")

    # Convert to records and clean
    print("\n🧹 Converting to clean records...")
    records = clean_df.to_dict('records')

    # Clean each record
    clean_records = []
    for i, record in enumerate(records[:10]):  # Test with first 10
        clean_record = {}
        for key, value in record.items():
            clean_record[key] = clean_value(value)
        clean_records.append(clean_record)

    print("\n📤 Prepared sample batch (first 5 records).")
    test_batch = clean_records[:5]

    # Debug: show data types
    print("\n🔍 Data types in first record:")
    for k, v in test_batch[0].items():
        if v is not None:
            print(f"   {k}: {v} ({type(v).__name__})")

    if args.dry_run:
        print("\n✅ Dry run complete.")
        return

    try:
        result = supabase.table('mlb_pitches_enhanced').insert(test_batch).execute()
        print("\n✅ Test successful! 5 records inserted.")

        # Ask to continue
        if args.auto_confirm:
            response = "yes"
        else:
            response = input("\nUpload full dataset now? (yes/no): ")

        if response.lower() == 'yes':
            # Process all records
            print("\n🧹 Processing all records...")
            all_clean_records = []

            for record in tqdm(records, desc="Cleaning records"):
                clean_record = {}
                for key, value in record.items():
                    clean_record[key] = clean_value(value)
                all_clean_records.append(clean_record)

            # Upload in batches
            batch_size = 1000
            failed = []
            successful = 0

            print(f"\n📤 Uploading {len(all_clean_records):,} records in batches...")
            for i in tqdm(range(0, len(all_clean_records), batch_size), desc="Uploading"):
                batch = all_clean_records[i:i + batch_size]
                try:
                    supabase.table('mlb_pitches_enhanced').insert(batch).execute()
                    successful += len(batch)
                except Exception as e:
                    failed.append((i, str(e)[:100]))

            print(f"\n✅ Upload complete!")
            print(f"   Successful: {successful:,} records")
            print(f"   Failed batches: {len(failed)}")

            if failed:
                print("\nFirst few errors:")
                for i, err in failed[:3]:
                    print(f"   Batch {i//batch_size}: {err}")

    except Exception as e:
        print(f"\n❌ Test upload failed: {e}")

        # Try to parse the error
        if "invalid input syntax" in str(e):
            print("\n💡 Hint: Check that your Supabase table schema matches the data types")

        # Debug problematic values
        print("\n🔍 Checking for problematic values...")
        for record in test_batch[:1]:
            for k, v in record.items():
                if isinstance(v, float) and (np.isinf(v) or np.isnan(v)):
                    print(f"   Problem: {k} = {v}")

if __name__ == "__main__":
    main() 
