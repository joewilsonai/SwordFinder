#!/usr/bin/env python3
"""
Calculate percentiles for all pitch and swing metrics in the database
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv
import logging
from scipy import stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PercentileCalculator:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.distributions = {}
        
    def load_distributions(self):
        """Load all data to calculate distributions - do this once for efficiency"""
        logger.info("Loading distributions from database...")
        
        # Get all data (we need it for accurate percentiles)
        # In production, might want to sample or use a different approach
        all_data = []
        batch_size = 10000
        offset = 0
        
        while True:
            result = self.supabase.table('mlb_pitches_enhanced')\
                .select('pitch_type, release_speed, release_spin_rate, pfx_x, pfx_z, bat_speed, sword_score')\
                .range(offset, offset + batch_size - 1)\
                .execute()
            
            if not result.data:
                break
                
            all_data.extend(result.data)
            offset += batch_size
            logger.info(f"Loaded {len(all_data)} records...")
        
        df = pd.DataFrame(all_data)
        logger.info(f"Total records loaded: {len(df)}")
        
        # Calculate movement magnitude
        df['movement_total'] = np.sqrt(df['pfx_x']**2 + df['pfx_z']**2)
        
        # Overall distributions
        self.distributions['velo_overall'] = df['release_speed'].dropna().values
        self.distributions['spin_overall'] = df['release_spin_rate'].dropna().values
        self.distributions['movement_overall'] = df['movement_total'].dropna().values
        self.distributions['bat_speed_overall'] = df[df['bat_speed'] > 0]['bat_speed'].values
        self.distributions['bat_speed_sword'] = df[(df['sword_score'] > 0) & (df['bat_speed'] > 0)]['bat_speed'].values
        
        # Pitch type specific distributions
        pitch_types = df['pitch_type'].unique()
        for pitch_type in pitch_types:
            if pd.isna(pitch_type):
                continue
                
            pt_df = df[df['pitch_type'] == pitch_type]
            
            key = f'velo_{pitch_type}'
            self.distributions[key] = pt_df['release_speed'].dropna().values
            
            key = f'spin_{pitch_type}'
            self.distributions[key] = pt_df['release_spin_rate'].dropna().values
            
            key = f'movement_{pitch_type}'
            self.distributions[key] = pt_df['movement_total'].dropna().values
        
        logger.info(f"Loaded {len(self.distributions)} distributions")
    
    def calculate_percentile(self, value, distribution):
        """Calculate percentile rank of a value in a distribution"""
        if len(distribution) == 0:
            return None
        return stats.percentileofscore(distribution, value, kind='rank')
    
    def process_batch(self, batch_data):
        """Process a batch of records and calculate all percentiles"""
        df = pd.DataFrame(batch_data)
        
        # Calculate movement magnitude
        df['movement_total'] = np.sqrt(df['pfx_x']**2 + df['pfx_z']**2)
        
        updates = []
        
        for idx, row in df.iterrows():
            update = {'id': row['id']}
            
            # Velocity percentiles
            if pd.notna(row.get('release_speed')):
                update['velo_percentile_overall'] = self.calculate_percentile(
                    row['release_speed'], 
                    self.distributions['velo_overall']
                )
                
                # Pitch type specific
                pt_key = f'velo_{row["pitch_type"]}'
                if pt_key in self.distributions and len(self.distributions[pt_key]) >= 100:
                    update['velo_percentile_pitch_type'] = self.calculate_percentile(
                        row['release_speed'],
                        self.distributions[pt_key]
                    )
            
            # Spin rate percentiles
            if pd.notna(row.get('release_spin_rate')):
                update['spin_percentile_overall'] = self.calculate_percentile(
                    row['release_spin_rate'],
                    self.distributions['spin_overall']
                )
                
                pt_key = f'spin_{row["pitch_type"]}'
                if pt_key in self.distributions and len(self.distributions[pt_key]) >= 100:
                    update['spin_percentile_pitch_type'] = self.calculate_percentile(
                        row['release_spin_rate'],
                        self.distributions[pt_key]
                    )
            
            # Movement percentiles
            if pd.notna(row.get('movement_total')):
                update['movement_percentile_overall'] = self.calculate_percentile(
                    row['movement_total'],
                    self.distributions['movement_overall']
                )
                
                pt_key = f'movement_{row["pitch_type"]}'
                if pt_key in self.distributions and len(self.distributions[pt_key]) >= 100:
                    update['movement_percentile_pitch_type'] = self.calculate_percentile(
                        row['movement_total'],
                        self.distributions[pt_key]
                    )
            
            # Bat speed percentiles
            if pd.notna(row.get('bat_speed')) and row['bat_speed'] > 0:
                update['bat_speed_percentile_overall'] = self.calculate_percentile(
                    row['bat_speed'],
                    self.distributions['bat_speed_overall']
                )
                
                # For sword percentile - LOWER is WORSE (invert)
                if row.get('sword_score', 0) > 0:
                    percentile = self.calculate_percentile(
                        row['bat_speed'],
                        self.distributions['bat_speed_sword']
                    )
                    update['bat_speed_percentile_sword'] = 100 - percentile
            
            updates.append(update)
        
        return updates
    
    def update_database(self, updates):
        """Update database with calculated percentiles"""
        for update in updates:
            # Remove id from update dict
            record_id = update.pop('id')
            
            # Only update if we have values to update
            if len(update) > 0:
                self.supabase.table('mlb_pitches_enhanced')\
                    .update(update)\
                    .eq('id', record_id)\
                    .execute()

def main():
    """Calculate percentiles for entire database"""
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    calculator = PercentileCalculator(supabase)
    
    print("📊 Percentile Calculator for MLB Pitches")
    print("=" * 50)
    
    # Load distributions (this takes time but is necessary)
    print("\n📂 Loading distributions...")
    calculator.load_distributions()
    
    # Process in batches
    print("\n🔄 Processing percentiles...")
    batch_size = 1000
    offset = 0
    total_processed = 0
    
    while True:
        # Get batch
        result = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .range(offset, offset + batch_size - 1)\
            .execute()
        
        if not result.data:
            break
        
        # Calculate percentiles
        updates = calculator.process_batch(result.data)
        
        # Update database
        calculator.update_database(updates)
        
        total_processed += len(result.data)
        offset += batch_size
        
        # Progress
        if total_processed % 10000 == 0:
            print(f"Processed {total_processed:,} records...")
    
    print("\n" + "=" * 50)
    print(f"✅ Complete! Processed {total_processed:,} records")
    
    # Show some stats
    print("\n📈 Sample Results:")
    
    # Fastest pitches
    fast = supabase.table('mlb_pitches_enhanced')\
        .select('pitcher_name, release_speed, velo_percentile_overall')\
        .gt('velo_percentile_overall', 99)\
        .order('release_speed', desc=True)\
        .limit(5)\
        .execute()
    
    if fast.data:
        print("\n🔥 Fastest pitches (99th percentile):")
        for pitch in fast.data:
            print(f"   {pitch['pitcher_name']}: {pitch['release_speed']} mph ({pitch['velo_percentile_overall']:.1f}%ile)")
    
    # Worst sword swings
    swords = supabase.table('mlb_pitches_enhanced')\
        .select('player_name, bat_speed, bat_speed_percentile_sword')\
        .gt('bat_speed_percentile_sword', 99)\
        .order('bat_speed')\
        .limit(5)\
        .execute()
    
    if swords.data:
        print("\n🗡️ Worst sword swings (99th percentile bad):")
        for swing in swords.data:
            print(f"   {swing['player_name']}: {swing['bat_speed']} mph ({swing['bat_speed_percentile_sword']:.1f}%ile worst)")

if __name__ == "__main__":
    main() 