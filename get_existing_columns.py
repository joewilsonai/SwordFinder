#!/usr/bin/env python3
"""Get list of existing columns in mlb_pitches_enhanced table"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_ANON_KEY')

if not supabase_url or not supabase_key:
    print("Missing Supabase credentials")
    exit(1)

supabase = create_client(supabase_url, supabase_key)

# Get a single row to see column structure
result = supabase.table('mlb_pitches_enhanced').select('*').limit(1).execute()

if result.data:
    columns = list(result.data[0].keys())
    print(f"Total columns in database: {len(columns)}")
    print("\nColumns:")
    for col in sorted(columns):
        print(f"  - {col}")
else:
    print("No data found in table")

# Check for specific columns
check_columns = ['age_bat', 'age_pit', 'age_bat_legacy', 'age_pit_legacy', 'is_sword_candidate']
print(f"\nChecking specific columns:")
for col in check_columns:
    if result.data and col in result.data[0]:
        print(f"  ✓ {col}")
    else:
        print(f"  ✗ {col}") 