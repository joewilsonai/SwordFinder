#!/usr/bin/env python3
"""Check the current status of all calculations in the database."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Try to load .env from parent directory if not in current
if not Path('.env').exists() and Path('../.env').exists():
    load_dotenv('../.env')
else:
    load_dotenv()

# Get Supabase credentials
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')

if not supabase_url or not supabase_key:
    print("Error: Supabase credentials not found in environment variables")
    sys.exit(1)

# Initialize Supabase client
supabase = create_client(supabase_url, supabase_key)

print("🔍 Checking database status...")
print("=" * 60)

# Check total records
total = supabase.table('mlb_pitches_enhanced').select('id', count='exact').execute()
print(f'Total records: {total.count:,}')

# Check perceived velocity progress
pv_done = supabase.table('mlb_pitches_enhanced').select('id', count='exact').not_.is_('perceived_velocity', 'null').execute()
print(f'\n📊 Perceived velocity calculated: {pv_done.count:,} ({pv_done.count/total.count*100:.1f}%)')

# Check strike zone distance progress  
sz_done = supabase.table('mlb_pitches_enhanced').select('id', count='exact').not_.is_('strike_zone_distance_inches', 'null').execute()
print(f'📏 Strike zone distance calculated: {sz_done.count:,} ({sz_done.count/total.count*100:.1f}%)')

# Check percentile calculations
print("\n📈 Percentile calculations:")
percentile_fields = ['velocity_percentile', 'spin_rate_percentile', 'h_break_percentile', 'v_break_percentile']
all_percentiles_done = True
for field in percentile_fields:
    done = supabase.table('mlb_pitches_enhanced').select('id', count='exact').not_.is_(field, 'null').execute()
    print(f'  {field}: {done.count:,} ({done.count/total.count*100:.1f}%)')
    if done.count < total.count:
        all_percentiles_done = False

# Check sword scores
sword_done = supabase.table('mlb_pitches_enhanced').select('id', count='exact').gt('sword_score', 0).execute()
print(f'\n⚔️  Sword scores calculated: {sword_done.count:,}')

# Check videos processed
video_done = supabase.table('mlb_pitches_enhanced').select('id', count='exact').not_.is_('video_azure_blob_url', 'null').execute()
print(f'🎥 Videos processed: {video_done.count:,}')

print("\n" + "=" * 60)
print("📋 Next steps:")
if pv_done.count < total.count:
    print(f"1. Complete perceived velocity calculation ({total.count - pv_done.count:,} remaining)")
if sz_done.count < total.count:
    print(f"2. Complete strike zone distance calculation ({total.count - sz_done.count:,} remaining)")
if not all_percentiles_done:
    print("3. Run percentile calculations")
print("4. Continue processing sword videos")
print("5. Set up API/UI for accessing the data")
