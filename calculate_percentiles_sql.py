#!/usr/bin/env python3
"""
Calculate percentiles using SQL window functions - MUCH faster!
"""

import os
from supabase import create_client
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_percentile_update(supabase, field_name, percentile_field, condition=""):
    """Run a single percentile update using SQL"""
    
    sql = f"""
    UPDATE mlb_pitches_enhanced
    SET {percentile_field} = subquery.percentile
    FROM (
        SELECT id,
               PERCENT_RANK() OVER (ORDER BY {field_name}) * 100 as percentile
        FROM mlb_pitches_enhanced
        WHERE {field_name} IS NOT NULL {condition}
    ) as subquery
    WHERE mlb_pitches_enhanced.id = subquery.id
    """
    
    logger.info(f"Updating {percentile_field}...")
    result = supabase.rpc('execute_sql', {'query': sql}).execute()
    return result

def run_pitch_type_percentile(supabase, field_name, percentile_field):
    """Calculate percentiles within pitch types"""
    
    sql = f"""
    UPDATE mlb_pitches_enhanced
    SET {percentile_field} = subquery.percentile
    FROM (
        SELECT id,
               PERCENT_RANK() OVER (
                   PARTITION BY pitch_type 
                   ORDER BY {field_name}
               ) * 100 as percentile
        FROM mlb_pitches_enhanced
        WHERE {field_name} IS NOT NULL
          AND pitch_type IS NOT NULL
    ) as subquery
    WHERE mlb_pitches_enhanced.id = subquery.id
    """
    
    logger.info(f"Updating {percentile_field} by pitch type...")
    result = supabase.rpc('execute_sql', {'query': sql}).execute()
    return result

def calculate_movement_and_percentiles(supabase):
    """Calculate movement magnitude and its percentiles"""
    
    # First add movement calculation
    sql = """
    UPDATE mlb_pitches_enhanced
    SET movement_total = SQRT(POWER(pfx_x, 2) + POWER(pfx_z, 2))
    WHERE pfx_x IS NOT NULL AND pfx_z IS NOT NULL
    """
    
    logger.info("Calculating movement magnitude...")
    supabase.rpc('execute_sql', {'query': sql}).execute()
    
    # Then calculate percentiles
    run_percentile_update(supabase, 'movement_total', 'movement_percentile_overall')
    run_pitch_type_percentile(supabase, 'movement_total', 'movement_percentile_pitch_type')

def calculate_sword_percentiles(supabase):
    """Calculate inverted percentiles for sword swings"""
    
    sql = """
    UPDATE mlb_pitches_enhanced
    SET bat_speed_percentile_sword = subquery.percentile
    FROM (
        SELECT id,
               (1 - PERCENT_RANK() OVER (ORDER BY bat_speed)) * 100 as percentile
        FROM mlb_pitches_enhanced
        WHERE bat_speed > 0
          AND sword_score > 0
    ) as subquery
    WHERE mlb_pitches_enhanced.id = subquery.id
    """
    
    logger.info("Updating sword percentiles (inverted)...")
    result = supabase.rpc('execute_sql', {'query': sql}).execute()
    return result

def main():
    """Calculate all percentiles using SQL - much faster than Python"""
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        logger.error("Missing Supabase credentials")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    print("📊 SQL-Based Percentile Calculator")
    print("=" * 50)
    print("\nNOTE: This requires a custom SQL function in Supabase.")
    print("Add this function to your Supabase SQL Editor first:")
    print("""
    CREATE OR REPLACE FUNCTION execute_sql(query text)
    RETURNS void AS $$
    BEGIN
        EXECUTE query;
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)
    
    response = input("\nHave you added the SQL function? (y/n): ")
    if response.lower() != 'y':
        print("Please add the function first!")
        return
    
    print("\n🔄 Calculating percentiles...")
    
    try:
        # 1. Velocity percentiles
        print("\n⚡ Velocity percentiles...")
        run_percentile_update(supabase, 'release_speed', 'velo_percentile_overall')
        run_pitch_type_percentile(supabase, 'release_speed', 'velo_percentile_pitch_type')
        
        # 2. Spin rate percentiles
        print("\n🌀 Spin rate percentiles...")
        run_percentile_update(supabase, 'release_spin_rate', 'spin_percentile_overall')
        run_pitch_type_percentile(supabase, 'release_spin_rate', 'spin_percentile_pitch_type')
        
        # 3. Movement percentiles
        print("\n📐 Movement percentiles...")
        calculate_movement_and_percentiles(supabase)
        
        # 4. Bat speed percentiles
        print("\n🏏 Bat speed percentiles...")
        run_percentile_update(supabase, 'bat_speed', 'bat_speed_percentile_overall', 
                            "AND bat_speed > 0")
        calculate_sword_percentiles(supabase)
        
        # 5. Extension percentiles
        print("\n📏 Extension percentiles...")
        run_percentile_update(supabase, 'release_extension', 'extension_percentile_overall')
        run_pitch_type_percentile(supabase, 'release_extension', 'extension_percentile_pitch_type')
        
        # 6. Perceived velocity percentiles (if column exists)
        print("\n⚡ Perceived velocity percentiles...")
        try:
            run_percentile_update(supabase, 'perceived_velocity', 'perceived_velo_percentile_overall')
            run_pitch_type_percentile(supabase, 'perceived_velocity', 'perceived_velo_percentile_pitch_type')
        except:
            print("   Perceived velocity not calculated yet - run calculate_perceived_velocity.py first")
        
        print("\n✅ All percentiles calculated!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nIf you got an RPC error, you need to add the SQL function first.")
        return
    
    # Show some results
    print("\n📈 Sample Results:")
    
    # Fastest pitches
    fast = supabase.table('mlb_pitches_enhanced')\
        .select('pitcher_name, pitch_type, release_speed, velo_percentile_overall, velo_percentile_pitch_type')\
        .gt('velo_percentile_overall', 99.5)\
        .order('release_speed', desc=True)\
        .limit(5)\
        .execute()
    
    if fast.data:
        print("\n🔥 Fastest pitches (99.5th percentile):")
        for pitch in fast.data:
            overall = pitch.get('velo_percentile_overall', 0)
            by_type = pitch.get('velo_percentile_pitch_type', 0)
            print(f"   {pitch['pitcher_name']}: {pitch['release_speed']} mph {pitch['pitch_type']}")
            print(f"      Overall: {overall:.1f}%ile, For {pitch['pitch_type']}: {by_type:.1f}%ile")
    
    # High spin breaking balls
    spin = supabase.table('mlb_pitches_enhanced')\
        .select('pitcher_name, pitch_type, release_spin_rate, spin_percentile_pitch_type')\
        .in_('pitch_type', ['SL', 'CU', 'KC'])\
        .gt('spin_percentile_pitch_type', 95)\
        .order('release_spin_rate', desc=True)\
        .limit(5)\
        .execute()
    
    if spin.data:
        print("\n🌀 Highest spin breaking balls (95th percentile for type):")
        for pitch in spin.data:
            print(f"   {pitch['pitcher_name']}: {pitch['release_spin_rate']} rpm {pitch['pitch_type']} ({pitch['spin_percentile_pitch_type']:.1f}%ile)")

if __name__ == "__main__":
    main() 