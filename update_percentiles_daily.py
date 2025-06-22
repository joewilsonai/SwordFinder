#!/usr/bin/env python3
"""
Update percentiles for daily new data efficiently
Uses existing distributions to approximate percentiles for new pitches
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv
import logging
import json
from scipy import stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DailyPercentileUpdater:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.distributions = {}
        self.distribution_stats = {}
        
    def load_or_create_distribution_cache(self):
        """Load cached distribution statistics or create them"""
        cache_file = 'percentile_distributions_cache.json'
        
        if os.path.exists(cache_file):
            # Check if cache is recent (within 7 days)
            cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
            if cache_age.days < 7:
                logger.info("Loading distribution cache...")
                with open(cache_file, 'r') as f:
                    self.distribution_stats = json.load(f)
                return True
        
        logger.info("Building distribution cache from database...")
        self.build_distribution_cache()
        
        # Save cache
        with open(cache_file, 'w') as f:
            json.dump(self.distribution_stats, f)
        
        return True
    
    def build_distribution_cache(self):
        """Build percentile lookup tables from existing data"""
        
        # Get percentile values for each metric
        metrics = [
            ('release_speed', 'velo'),
            ('release_spin_rate', 'spin'),
            ('bat_speed', 'bat_speed'),
            ('release_extension', 'extension'),
            ('perceived_velocity', 'perceived_velo')
        ]
        
        # Also need movement distributions
        movement_sql = """
        SELECT 
            PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p1,
            PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p5,
            PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p10,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p50,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p75,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p90,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p95,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p99,
            COUNT(*) as count
        FROM mlb_pitches_enhanced
        WHERE pfx_x IS NOT NULL AND pfx_z IS NOT NULL
        """
        
        result = self.supabase.rpc('execute_sql_query', {'query': movement_sql}).execute()
        if result.data:
            self.distribution_stats['movement_overall'] = result.data[0]
        
        # Movement by pitch type
        movement_by_type_sql = """
        SELECT 
            pitch_type,
            PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p1,
            PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p5,
            PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p10,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p50,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p75,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p90,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p95,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))) as p99,
            COUNT(*) as count
        FROM mlb_pitches_enhanced
        WHERE pfx_x IS NOT NULL AND pfx_z IS NOT NULL AND pitch_type IS NOT NULL
        GROUP BY pitch_type
        HAVING COUNT(*) >= 100
        """
        
        result = self.supabase.rpc('execute_sql_query', {'query': movement_by_type_sql}).execute()
        if result.data:
            for row in result.data:
                pt = row['pitch_type']
                self.distribution_stats[f'movement_{pt}'] = row
        
        for field, prefix in metrics:
            # Overall distribution
            sql = f"""
            SELECT 
                PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY {field}) as p1,
                PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY {field}) as p5,
                PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY {field}) as p10,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {field}) as p25,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {field}) as p50,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {field}) as p75,
                PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY {field}) as p90,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {field}) as p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY {field}) as p99,
                COUNT(*) as count,
                AVG({field}) as mean,
                STDDEV({field}) as stddev
            FROM mlb_pitches_enhanced
            WHERE {field} IS NOT NULL
            """
            
            if field == 'bat_speed':
                sql += " AND bat_speed > 0"
            
            result = self.supabase.rpc('execute_sql_query', {'query': sql}).execute()
            if result.data:
                self.distribution_stats[f'{prefix}_overall'] = result.data[0]
            
            # By pitch type
            if field != 'bat_speed':
                sql_by_type = f"""
                SELECT 
                    pitch_type,
                    PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY {field}) as p1,
                    PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY {field}) as p5,
                    PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY {field}) as p10,
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {field}) as p25,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {field}) as p50,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {field}) as p75,
                    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY {field}) as p90,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {field}) as p95,
                    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY {field}) as p99,
                    COUNT(*) as count
                FROM mlb_pitches_enhanced
                WHERE {field} IS NOT NULL AND pitch_type IS NOT NULL
                GROUP BY pitch_type
                HAVING COUNT(*) >= 100
                """
                
                result = self.supabase.rpc('execute_sql_query', {'query': sql}).execute()
                if result.data:
                    for row in result.data:
                        pt = row['pitch_type']
                        self.distribution_stats[f'{prefix}_{pt}'] = row
    
    def estimate_percentile(self, value, dist_key):
        """Estimate percentile using cached distribution statistics"""
        if dist_key not in self.distribution_stats:
            return None
        
        stats = self.distribution_stats[dist_key]
        
        # Use linear interpolation between known percentiles
        percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
        values = [stats[f'p{p}'] for p in percentiles]
        
        # Handle edge cases
        if value <= values[0]:
            return 1.0
        if value >= values[-1]:
            return 99.0
        
        # Find surrounding percentiles and interpolate
        for i in range(len(values) - 1):
            if values[i] <= value <= values[i + 1]:
                # Linear interpolation
                pct_low = percentiles[i]
                pct_high = percentiles[i + 1]
                val_low = values[i]
                val_high = values[i + 1]
                
                if val_high == val_low:
                    return pct_low
                
                ratio = (value - val_low) / (val_high - val_low)
                return pct_low + ratio * (pct_high - pct_low)
        
        return 50.0  # Fallback
    
    def update_daily_percentiles(self, date_str=None):
        """Update percentiles for a specific date's data"""
        
        if date_str is None:
            # Default to yesterday
            date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        logger.info(f"Updating percentiles for {date_str}")
        
        # Get all pitches from that date
        result = self.supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .eq('game_date', date_str)\
            .execute()
        
        if not result.data:
            logger.info(f"No data found for {date_str}")
            return 0
        
        df = pd.DataFrame(result.data)
        logger.info(f"Processing {len(df)} pitches from {date_str}")
        
        # Calculate movement if needed
        df['movement_total'] = np.sqrt(df['pfx_x']**2 + df['pfx_z']**2)
        
        updates = []
        
        for idx, row in df.iterrows():
            update = {'id': row['id']}
            
            # Velocity percentiles
            if pd.notna(row.get('release_speed')):
                update['velo_percentile_overall'] = self.estimate_percentile(
                    row['release_speed'], 'velo_overall'
                )
                
                if row.get('pitch_type') and f'velo_{row["pitch_type"]}' in self.distribution_stats:
                    update['velo_percentile_pitch_type'] = self.estimate_percentile(
                        row['release_speed'], f'velo_{row["pitch_type"]}'
                    )
            
            # Spin rate percentiles
            if pd.notna(row.get('release_spin_rate')):
                update['spin_percentile_overall'] = self.estimate_percentile(
                    row['release_spin_rate'], 'spin_overall'
                )
                
                if row.get('pitch_type') and f'spin_{row["pitch_type"]}' in self.distribution_stats:
                    update['spin_percentile_pitch_type'] = self.estimate_percentile(
                        row['release_spin_rate'], f'spin_{row["pitch_type"]}'
                    )
            
            # Bat speed percentiles
            if pd.notna(row.get('bat_speed')) and row['bat_speed'] > 0:
                update['bat_speed_percentile_overall'] = self.estimate_percentile(
                    row['bat_speed'], 'bat_speed_overall'
                )
                
                # For sword swings, calculate inverted percentile
                if row.get('sword_score', 0) > 0:
                    # Get sword distribution
                    if 'bat_speed_sword' not in self.distribution_stats:
                        # Build it on demand
                        self.build_sword_distribution()
                    
                    if 'bat_speed_sword' in self.distribution_stats:
                        percentile = self.estimate_percentile(
                            row['bat_speed'], 'bat_speed_sword'
                        )
                        update['bat_speed_percentile_sword'] = 100 - percentile
            
            # Movement percentiles
            if pd.notna(row.get('movement_total')):
                update['movement_percentile_overall'] = self.estimate_percentile(
                    row['movement_total'], 'movement_overall'
                )
                
                if row.get('pitch_type') and f'movement_{row["pitch_type"]}' in self.distribution_stats:
                    update['movement_percentile_pitch_type'] = self.estimate_percentile(
                        row['movement_total'], f'movement_{row["pitch_type"]}'
                    )
            
            # Extension percentiles
            if pd.notna(row.get('release_extension')):
                update['extension_percentile_overall'] = self.estimate_percentile(
                    row['release_extension'], 'extension_overall'
                )
                
                if row.get('pitch_type') and f'extension_{row["pitch_type"]}' in self.distribution_stats:
                    update['extension_percentile_pitch_type'] = self.estimate_percentile(
                        row['release_extension'], f'extension_{row["pitch_type"]}'
                    )
            
            # Perceived velocity percentiles (if available)
            if pd.notna(row.get('perceived_velocity')):
                update['perceived_velo_percentile_overall'] = self.estimate_percentile(
                    row['perceived_velocity'], 'perceived_velo_overall'
                )
                
                if row.get('pitch_type') and f'perceived_velo_{row["pitch_type"]}' in self.distribution_stats:
                    update['perceived_velo_percentile_pitch_type'] = self.estimate_percentile(
                        row['perceived_velocity'], f'perceived_velo_{row["pitch_type"]}'
                    )
            
            updates.append(update)
        
        # Batch update
        for update in updates:
            record_id = update.pop('id')
            if len(update) > 0:
                self.supabase.table('mlb_pitches_enhanced')\
                    .update(update)\
                    .eq('id', record_id)\
                    .execute()
        
        logger.info(f"Updated {len(updates)} records with percentiles")
        return len(updates)
    
    def build_sword_distribution(self):
        """Build sword-specific bat speed distribution"""
        sql = """
        SELECT 
            PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY bat_speed) as p1,
            PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY bat_speed) as p5,
            PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY bat_speed) as p10,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY bat_speed) as p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY bat_speed) as p50,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY bat_speed) as p75,
            PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY bat_speed) as p90,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY bat_speed) as p95,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY bat_speed) as p99,
            COUNT(*) as count
        FROM mlb_pitches_enhanced
        WHERE bat_speed > 0 AND sword_score > 0
        """
        
        result = self.supabase.rpc('execute_sql_query', {'query': sql}).execute()
        if result.data:
            self.distribution_stats['bat_speed_sword'] = result.data[0]
    
    def refresh_cache_weekly(self):
        """Refresh the distribution cache weekly"""
        cache_file = 'percentile_distributions_cache.json'
        
        if os.path.exists(cache_file):
            cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
            if cache_age.days >= 7:
                logger.info("Cache is stale, rebuilding...")
                os.remove(cache_file)
                self.load_or_create_distribution_cache()

def main():
    """Run daily percentile update"""
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    updater = DailyPercentileUpdater(supabase)
    
    print("📊 Daily Percentile Updater")
    print("=" * 50)
    
    # Load or create cache
    updater.load_or_create_distribution_cache()
    
    # Update yesterday's data by default
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Or specify a date
    import sys
    if len(sys.argv) > 1:
        date_to_update = sys.argv[1]
    else:
        date_to_update = yesterday
    
    print(f"\n📅 Updating percentiles for: {date_to_update}")
    
    count = updater.update_daily_percentiles(date_to_update)
    
    print(f"\n✅ Updated {count} records")
    
    # Refresh cache if needed
    updater.refresh_cache_weekly()

if __name__ == "__main__":
    main() 