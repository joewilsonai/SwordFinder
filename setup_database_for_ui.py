#!/usr/bin/env python3
"""
Setup database for UI development
Guides through adding missing columns and populating data
"""

import os
import sys
from dotenv import load_dotenv

def main():
    print("🚀 SwordFinder Database Setup for UI Development")
    print("=" * 60)
    
    load_dotenv()
    
    # Check environment
    if not os.getenv('SUPABASE_URL'):
        print("❌ Missing SUPABASE_URL in .env file")
        sys.exit(1)
    
    # Show which project we're connected to
    supabase_url = os.getenv('SUPABASE_URL', '')
    if 'seagurfpitfslyxxxztw' in supabase_url:
        print("✅ Connected to Supabase project: Swordfinder")
        print(f"   URL: {supabase_url}")
    else:
        print("⚠️  Warning: May not be connected to the correct Supabase project")
        print(f"   Current URL: {supabase_url}")
        print(f"   Expected: https://seagurfpitfslyxxxztw.supabase.co")
    
    print("\n📋 Step 1: Add Missing Columns")
    print("-" * 40)
    print("Please run the following SQL in your Supabase SQL Editor:")
    print("👉 https://app.supabase.com/project/seagurfpitfslyxxxztw/sql/new\n")
    
    with open('add_missing_columns.sql', 'r') as f:
        print(f.read())
    
    input("\n✅ Press Enter after running the SQL above...")
    
    print("\n📋 Step 2: Calculate Perceived Velocity")
    print("-" * 40)
    print("This will calculate perceived velocity for all pitches (~5 minutes)")
    
    response = input("Run calculate_perceived_velocity.py? (y/n): ")
    if response.lower() == 'y':
        os.system('python calculate_perceived_velocity.py')
    
    print("\n📋 Step 3: Calculate Strike Zone Distance")
    print("-" * 40)
    print("This will calculate strike zone distance for all pitches (~5 minutes)")
    
    response = input("Run calculate_strike_zone_distance.py? (y/n): ")
    if response.lower() == 'y':
        os.system('python calculate_strike_zone_distance.py')
    
    print("\n📋 Step 4: Calculate All Percentiles")
    print("-" * 40)
    print("This will calculate percentiles for all metrics (~10 minutes)")
    
    response = input("Run calculate_percentiles_sql.py? (y/n): ")
    if response.lower() == 'y':
        os.system('python calculate_percentiles_sql.py')
    
    print("\n📋 Step 5: Verify Sword Scores")
    print("-" * 40)
    print("Checking if sword scores need to be calculated...")
    
    response = input("Run calculate_all_sword_scores.py? (y/n): ")
    if response.lower() == 'y':
        os.system('python calculate_all_sword_scores.py')
    
    print("\n📋 Step 6: Test Daily Update")
    print("-" * 40)
    print("This will test the daily update script")
    
    response = input("Test daily_update.py? (y/n): ")
    if response.lower() == 'y':
        os.system('python daily_update.py')
    
    print("\n✅ Database setup complete!")
    print("\nNext steps:")
    print("1. Create api.py with FastAPI")
    print("2. Build your UI!")

if __name__ == "__main__":
    main() 