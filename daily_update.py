#!/usr/bin/env python3
"""
Daily MLB Data Update Script
Runs at 1pm daily to fetch yesterday's MLB data and insert into Supabase
"""

import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pybaseball import statcast
from supabase import create_client
from dotenv import load_dotenv
import logging
from typing import Optional, List
from update_percentiles_daily import DailyPercentileUpdater
from env_config import get_env

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_update.log'),
        logging.StreamHandler()
    ]
)

def get_yesterday_data() -> Optional[pd.DataFrame]:
    """Download yesterday's MLB data from pybaseball"""
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    logging.info(f"Fetching MLB data for {date_str}")
    
    try:
        # Get yesterday's data
        df = statcast(
            start_dt=date_str,
            end_dt=date_str,
            verbose=False
        )
        
        if df.empty:
            logging.warning(f"No data found for {date_str}")
            return None
            
        logging.info(f"Found {len(df)} pitches for {date_str}")
        return df
        
    except Exception as e:
        logging.error(f"Error fetching data: {e}")
        return None

def get_existing_columns(supabase) -> List[str]:
    """Get list of columns that exist in the database"""
    try:
        # Get one row to see structure
        result = supabase.table('mlb_pitches_enhanced').select('*').limit(1).execute()
        if result.data:
            return list(result.data[0].keys())
        else:
            # If no data, return empty list (will fail upload but safely)
            return []
    except Exception as e:
        logging.error(f"Error getting columns: {e}")
        return []

def prepare_data_for_upload(df: pd.DataFrame, supabase=None) -> pd.DataFrame:
    """Clean and prepare data for Supabase upload"""
    # Replace infinity values
    df = df.replace([float('inf'), float('-inf')], None)
    
    # If supabase client provided, filter to existing columns
    if supabase:
        existing_columns = get_existing_columns(supabase)
        if existing_columns:
            # Filter to only columns that exist in database
            df_columns = set(df.columns)
            db_columns = set(existing_columns)
            columns_to_keep = list(df_columns.intersection(db_columns))
            
            # Log what we're dropping
            dropped_columns = df_columns - db_columns
            if dropped_columns:
                logging.warning(f"Dropping {len(dropped_columns)} columns not in database")
            
            # Keep only columns that exist in database
            df = df[columns_to_keep].copy()
    
    # Convert to proper types
    int_columns = ['pitcher', 'batter', 'outs_when_up', 'strikes', 'balls', 
                   'sz_top', 'sz_bot', 'hit_location', 'bb_type', 'pitch_number']
    for col in int_columns:
        if col in df.columns:
            # Convert to numeric, handling errors
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Convert on_base columns from player IDs to boolean
    on_base_columns = ['on_1b', 'on_2b', 'on_3b']
    for col in on_base_columns:
        if col in df.columns:
            df[col] = df[col].notna()
    
    # Ensure game_date is datetime
    if 'game_date' in df.columns:
        df['game_date'] = pd.to_datetime(df['game_date'])

    # Populate pitcher_name and batter_name columns.
    # Statcast convention: player_name = PITCHER's name. There is no batter_name in raw data —
    # we resolve it from the batter ID via MLB Stats API (cached locally).
    if 'player_name' in df.columns:
        df['pitcher_name'] = df['player_name']

    if 'batter' in df.columns:
        try:
            from resolve_player_names import resolve_names
            unique_batters = [int(x) for x in df['batter'].dropna().unique()]
            name_map = resolve_names(unique_batters)
            df['batter_name'] = df['batter'].map(lambda b: name_map.get(int(b)) if pd.notna(b) else None)
            logging.info(f"Resolved {len(name_map)}/{len(unique_batters)} batter names")
        except Exception as e:
            logging.warning(f"batter_name resolution failed: {e}")
            df['batter_name'] = None

    return df

def calculate_perceived_velocity_simple(actual_velocity, extension):
    """Calculate perceived velocity based on extension"""
    if pd.isna(actual_velocity) or pd.isna(extension):
        return None
    
    MOUND_DISTANCE = 60.5
    effective_distance = MOUND_DISTANCE - extension
    
    if effective_distance <= 0:
        return None
    
    perceived = actual_velocity * (MOUND_DISTANCE / effective_distance)
    return round(perceived, 1)

def calculate_strike_zone_distance_simple(plate_x, plate_z, sz_top, sz_bot):
    """Calculate minimum distance from strike zone edge in inches"""
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

def calculate_sword_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Add sword candidate identification to the dataframe"""
    # Check for sword swing criteria
    df['is_sword_candidate'] = (
        df['description'].str.contains('swinging_strike', case=False, na=False) & 
        (df['bat_speed'] < 60) & 
        (df['bat_speed'] > 0) &  # Must have bat tracking
        (df['strikes'] == 2)  # Two-strike count
    )
    
    # Calculate sword score for candidates
    def calculate_sword_score(row):
        # Handle NA values explicitly to avoid ambiguity
        if pd.isna(row['is_sword_candidate']) or not row['is_sword_candidate'] or pd.isna(row['bat_speed']):
            return None
            
        # Simple sword score calculation
        bat_speed_score = (60 - row['bat_speed']) / 60 * 50  # 0-50 points
        
        # Add swing path tilt if available
        tilt_score = 0
        if pd.notna(row.get('swing_path_tilt', None)):
            tilt_score = min(row['swing_path_tilt'] / 60 * 25, 25)  # 0-25 points
        
        # Add timing penalty for late swings
        timing_score = 0
        if pd.notna(row.get('swing_length', None)):
            timing_score = min(row['swing_length'] / 10 * 25, 25)  # 0-25 points
            
        return 50 + bat_speed_score + tilt_score + timing_score
    
    df['sword_score'] = df.apply(calculate_sword_score, axis=1)
    
    return df

def upload_to_supabase(df: pd.DataFrame) -> bool:
    """Upload data to Supabase, handling duplicates"""
    load_dotenv()
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logging.error("Missing Supabase credentials")
        return False
    
    try:
        supabase = create_client(supabase_url, supabase_key)
        
        # Filter data to only columns that exist in database
        df = prepare_data_for_upload(df, supabase)
        
        # Convert to dict and handle NaN values
        records = df.to_dict('records')
        for record in records:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
                # Handle Timestamp objects
                elif hasattr(value, 'isoformat'):
                    record[key] = value.isoformat()
                elif isinstance(value, pd.Timestamp):
                    record[key] = value.isoformat()
        
        # Upload in batches of 50
        batch_size = 50
        total_uploaded = 0
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            # Insert new records (duplicates unlikely for yesterday's data)
            # If we need to handle duplicates, we could add sv_id to the table
            # or use game_pk + at_bat_number + pitch_number as composite key
            result = supabase.table('mlb_pitches_enhanced').insert(
                batch
            ).execute()
            
            total_uploaded += len(batch)
            logging.info(f"Uploaded batch {i//batch_size + 1}: {len(batch)} records")
        
        logging.info(f"Successfully uploaded {total_uploaded} records to Supabase")
        return True
        
    except Exception as e:
        logging.error(f"Error uploading to Supabase: {e}")
        return False

def send_notification(success: bool, records_count: int = 0):
    """Send notification about the update status"""
    if success:
        message = f"✅ Daily update successful! Added {records_count} pitches."
    else:
        message = "❌ Daily update failed! Check logs for details."
    
    logging.info(f"Update status: {message}")
    
    # TODO: Add email/Slack/Discord notification here if desired
    # For now, just log it

def update_percentiles_for_date(date_str: str) -> bool:
    """Update percentiles for newly added data"""
    try:
        load_dotenv()
        
        supabase_url = get_env('SUPABASE_URL')
        supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')
        
        if not supabase_url or not supabase_key:
            logging.error("Missing Supabase credentials for percentile update")
            return False
        
        supabase = create_client(supabase_url, supabase_key)
        updater = DailyPercentileUpdater(supabase)
        
        # Load or create distribution cache
        updater.load_or_create_distribution_cache()
        
        # Update percentiles for the given date
        count = updater.update_daily_percentiles(date_str)
        logging.info(f"Updated percentiles for {count} records")
        
        # Refresh cache weekly
        updater.refresh_cache_weekly()
        
        return True
        
    except Exception as e:
        logging.error(f"Error updating percentiles: {e}")
        return False

def check_if_date_exists(date_str: str) -> bool:
    """Check if data for a specific date already exists in the database"""
    load_dotenv()
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        return False
    
    try:
        supabase = create_client(supabase_url, supabase_key)
        result = supabase.table('mlb_pitches_enhanced').select('id', count='exact').eq('game_date', date_str).execute()
        count = result.count or 0
        
        if count > 0:
            logging.info(f"Found {count} existing records for {date_str}")
            return True
        return False
    except Exception as e:
        logging.error(f"Error checking existing data: {e}")
        return False

def main():
    """Main execution function"""
    logging.info("Starting daily MLB data update...")
    
    # Store the date for later use
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    # Check if data already exists
    if check_if_date_exists(date_str):
        logging.info(f"Data for {date_str} already exists. Skipping update.")
        send_notification(True, 0)  # Success but no new records
        return
    
    # Get yesterday's data
    df = get_yesterday_data()
    
    if df is None or df.empty:
        logging.warning("No data to update")
        send_notification(False)
        return
    
    # Calculate sword candidates (before upload, since this adds columns)
    df = calculate_sword_candidates(df)
    
    # Calculate perceived velocity if extension data exists
    if 'release_extension' in df.columns and 'release_speed' in df.columns:
        df['perceived_velocity'] = df.apply(
            lambda row: calculate_perceived_velocity_simple(row['release_speed'], row['release_extension']),
            axis=1
        )
    
    # Calculate strike zone distance if location data exists
    if all(col in df.columns for col in ['plate_x', 'plate_z', 'sz_top', 'sz_bot']):
        df['strike_zone_distance_inches'] = df.apply(
            lambda row: calculate_strike_zone_distance_simple(
                row['plate_x'], row['plate_z'], row['sz_top'], row['sz_bot']
            ),
            axis=1
        )
    
    # Log sword candidates found
    sword_count = df['is_sword_candidate'].sum()
    logging.info(f"Found {sword_count} sword candidates in {len(df)} pitches")
    
    # Upload to Supabase
    success = upload_to_supabase(df)
    
    if success:
        # Update percentiles for the new data
        logging.info("Updating percentiles for new data...")
        percentile_success = update_percentiles_for_date(date_str)
        if not percentile_success:
            logging.warning("Failed to update percentiles, but data was uploaded successfully")
    
    # Send notification
    send_notification(success, len(df))
    
    # Log top swords if any
    if sword_count > 0:
        sword_df = df[df['is_sword_candidate']]
        if not sword_df.empty:
            top_swords = sword_df.nlargest(5, 'sword_score')
            logging.info("Top sword swings from yesterday:")
            for _, sword in top_swords.iterrows():
                logging.info(f"  {sword['player_name']}: {sword['bat_speed']:.1f} mph (score: {sword['sword_score']:.1f})")

if __name__ == "__main__":
    main() 
