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
from env_config import get_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PERCENTILE_POINTS = [1, 5, 10, 25, 50, 75, 90, 95, 99]
DIST_FIELDS = [
    "id",
    "pitch_type",
    "release_speed",
    "release_spin_rate",
    "pfx_x",
    "pfx_z",
    "bat_speed",
    "sword_score",
    "release_extension",
    "perceived_velocity",
]


class DailyPercentileUpdater:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.distributions = {}
        self.distribution_stats = {}
        
    @staticmethod
    def cache_file_for_year(year=None) -> str:
        return (
            f"percentile_distributions_cache_{year}.json"
            if year is not None
            else "percentile_distributions_cache.json"
        )

    def load_or_create_distribution_cache(self, year=None):
        """Load cached distribution statistics or create them"""
        cache_file = self.cache_file_for_year(year)
        
        if os.path.exists(cache_file):
            # Check if cache is recent (within 7 days)
            cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
            if cache_age.days < 7:
                logger.info("Loading distribution cache...")
                with open(cache_file, 'r') as f:
                    self.distribution_stats = json.load(f)
                return True
        
        logger.info("Building distribution cache from database...")
        self.build_distribution_cache(year=year)
        
        # Save cache
        with open(cache_file, 'w') as f:
            json.dump(self.distribution_stats, f)
        
        return True
    
    def build_distribution_cache(self, year=None):
        """Build percentile lookup tables from existing data"""
        try:
            self.build_distribution_cache_from_query_rpc(year=year)
        except Exception as exc:
            if not self.is_missing_query_rpc_error(exc):
                raise
            logger.warning(
                "execute_sql_query RPC is unavailable; building percentile "
                "distributions through Supabase table reads instead."
            )
            self.build_distribution_cache_from_table_rows(year=year)

    @staticmethod
    def is_missing_query_rpc_error(exc: Exception) -> bool:
        message = str(exc)
        return "execute_sql_query" in message and (
            "Could not find the function" in message
            or "PGRST202" in message
            or "not found" in message.lower()
        )

    def execute_query_sql(self, sql: str):
        return self.supabase.rpc('execute_sql_query', {'query': sql}).execute()

    @staticmethod
    def year_where_clause(year=None, prefix: str = "AND") -> str:
        if year is None:
            return ""
        return f" {prefix} game_date >= '{year}-01-01' AND game_date < '{year + 1}-01-01'"

    def build_distribution_cache_from_query_rpc(self, year=None):
        """Build percentile lookup tables with the optional SQL query RPC."""
        
        # Get percentile values for each metric
        metrics = [
            ('release_speed', 'velo'),
            ('release_spin_rate', 'spin'),
            ('bat_speed', 'bat_speed'),
            ('release_extension', 'extension'),
            ('perceived_velocity', 'perceived_velo')
        ]
        
        # Also need movement distributions
        movement_sql = f"""
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
        {self.year_where_clause(year)}
        """
        
        result = self.execute_query_sql(movement_sql)
        if result.data:
            self.distribution_stats['movement_overall'] = result.data[0]
        
        # Movement by pitch type
        movement_by_type_sql = f"""
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
        {self.year_where_clause(year)}
        GROUP BY pitch_type
        HAVING COUNT(*) >= 100
        """
        
        result = self.execute_query_sql(movement_by_type_sql)
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
            sql += self.year_where_clause(year)
            
            result = self.execute_query_sql(sql)
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
                {self.year_where_clause(year)}
                GROUP BY pitch_type
                HAVING COUNT(*) >= 100
                """
                
                result = self.execute_query_sql(sql_by_type)
                if result.data:
                    for row in result.data:
                        pt = row['pitch_type']
                        self.distribution_stats[f'{prefix}_{pt}'] = row

    @staticmethod
    def distribution_stats_from_series(series: pd.Series, include_moments: bool = True):
        """Return PERCENTILE_CONT-like stats for one numeric distribution."""
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if clean.empty:
            return None

        stats_row = {
            f"p{point}": float(clean.quantile(point / 100.0))
            for point in PERCENTILE_POINTS
        }
        stats_row["count"] = int(clean.count())
        if include_moments:
            stats_row["mean"] = float(clean.mean())
            stddev = clean.std()
            stats_row["stddev"] = float(stddev) if pd.notna(stddev) else 0.0
        return stats_row

    def fetch_distribution_rows(self, page_size: int = 5000, year=None) -> list:
        """Load fields needed to build percentile distributions without SQL RPC."""
        rows = []
        last_id = None

        while True:
            query = (
                self.supabase.table("mlb_pitches_enhanced")
                .select(",".join(DIST_FIELDS))
                .order("id")
            )
            if year is not None:
                query = query.gte("game_date", f"{year}-01-01").lt(
                    "game_date",
                    f"{year + 1}-01-01",
                )
            if last_id is not None:
                query = query.gt("id", last_id)

            result = query.range(0, page_size - 1).execute()
            page = result.data or []
            if not page:
                break

            rows.extend(page)
            last_id = page[-1].get("id")
            logger.info("Loaded %s rows for percentile distribution cache", len(rows))

            if len(page) < page_size:
                break

        return rows

    def build_distribution_cache_from_table_rows(self, year=None):
        """Build distribution stats from Supabase REST rows when query RPC is absent."""
        rows = self.fetch_distribution_rows(year=year)
        df = pd.DataFrame(rows)
        if df.empty:
            logger.warning("No rows available for percentile distribution cache")
            return

        for col in DIST_FIELDS:
            if col in {"id", "pitch_type"}:
                continue
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["movement_total"] = np.sqrt((df["pfx_x"] ** 2) + (df["pfx_z"] ** 2))

        movement = self.distribution_stats_from_series(df["movement_total"], include_moments=False)
        if movement:
            self.distribution_stats["movement_overall"] = movement

        movement_rows = df[df["movement_total"].notna() & df["pitch_type"].notna()]
        for pitch_type, group in movement_rows.groupby("pitch_type"):
            if len(group) < 100:
                continue
            stats_row = self.distribution_stats_from_series(
                group["movement_total"],
                include_moments=False,
            )
            if stats_row:
                stats_row["pitch_type"] = pitch_type
                self.distribution_stats[f"movement_{pitch_type}"] = stats_row

        metrics = [
            ("release_speed", "velo"),
            ("release_spin_rate", "spin"),
            ("bat_speed", "bat_speed"),
            ("release_extension", "extension"),
            ("perceived_velocity", "perceived_velo"),
        ]

        for field, prefix in metrics:
            values = df[field]
            if field == "bat_speed":
                values = values[values > 0]

            stats_row = self.distribution_stats_from_series(values)
            if stats_row:
                self.distribution_stats[f"{prefix}_overall"] = stats_row

            if field == "bat_speed":
                continue

            grouped = df[df[field].notna() & df["pitch_type"].notna()]
            for pitch_type, group in grouped.groupby("pitch_type"):
                if len(group) < 100:
                    continue
                stats_row = self.distribution_stats_from_series(group[field], include_moments=False)
                if stats_row:
                    stats_row["pitch_type"] = pitch_type
                    self.distribution_stats[f"{prefix}_{pitch_type}"] = stats_row

        sword_values = df[(df["bat_speed"] > 0) & (df["sword_score"] > 0)]["bat_speed"]
        sword_stats = self.distribution_stats_from_series(sword_values, include_moments=False)
        if sword_stats:
            self.distribution_stats["bat_speed_sword"] = sword_stats
    
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
        
        try:
            result = self.execute_query_sql(sql)
            if result.data:
                self.distribution_stats['bat_speed_sword'] = result.data[0]
        except Exception as exc:
            if not self.is_missing_query_rpc_error(exc):
                raise
            rows = self.fetch_distribution_rows()
            df = pd.DataFrame(rows)
            if df.empty:
                return
            df["bat_speed"] = pd.to_numeric(df["bat_speed"], errors="coerce")
            df["sword_score"] = pd.to_numeric(df["sword_score"], errors="coerce")
            sword_values = df[(df["bat_speed"] > 0) & (df["sword_score"] > 0)]["bat_speed"]
            sword_stats = self.distribution_stats_from_series(
                sword_values,
                include_moments=False,
            )
            if sword_stats:
                self.distribution_stats["bat_speed_sword"] = sword_stats
    
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
    
    supabase_url = get_env('SUPABASE_URL')
    supabase_key = get_env('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    updater = DailyPercentileUpdater(supabase)
    
    print("📊 Daily Percentile Updater")
    print("=" * 50)
    
    # Update yesterday's data by default
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Or specify a date
    import sys
    if len(sys.argv) > 1:
        date_to_update = sys.argv[1]
    else:
        date_to_update = yesterday

    # Load or create a cache scoped to the season being updated.
    updater.load_or_create_distribution_cache(year=int(date_to_update[:4]))
    
    print(f"\n📅 Updating percentiles for: {date_to_update}")
    
    count = updater.update_daily_percentiles(date_to_update)
    
    print(f"\n✅ Updated {count} records")
    
    # Refresh cache if needed
    updater.refresh_cache_weekly()

if __name__ == "__main__":
    main() 
