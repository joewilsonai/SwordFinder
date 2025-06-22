# SwordFinder - Complete Documentation

## 🎯 Project Overview

SwordFinder identifies and analyzes "sword swings" in baseball - strikeouts where batters have embarrassingly slow bat speeds on fastballs. With the new 2025 MLB bat tracking data, we can now find the worst swings in baseball and instantly get video clips.

### What Makes a True Sword Swing?
- **2-strike count** → Strikeout
- **Swinging strike** (not called)
- **Bat speed < 60 mph** (embarrassingly slow)
- **Swing path tilt > 30°** (bad swing plane)

## 🚀 Current Status (June 22, 2024)

### ⏳ Currently Running
- **Perceived Velocity Calculation**: 20,673 / 353,506 (5.8%) - ETA: ~10-12 hours
- **Strike Zone Boundaries**: 477 / 353,506 (0.1%) - ETA: ~2-3 hours
- **Strike Zone Distance**: Waiting for boundaries to complete

### ✅ Complete & Operational
- 353,506 MLB pitches (2025 season through June 21) in Supabase
- Enhanced table with 118+ MLB fields plus custom sword scoring
- Play ID mapping fixed (gets correct video for each pitch)
- 426 videos processed and uploaded to Azure
- Basic API with health check and recent swords endpoints
- Daily update script ready with all calculations integrated

## 📊 Database Schema

### Table: `mlb_pitches_enhanced`
```sql
-- Core MLB fields
game_pk, game_date, pitcher, batter, pitch_type, release_speed, etc.

-- 2025 Bat tracking  
bat_speed, swing_length, swing_path_tilt, attack_angle

-- Custom fields
sword_score              -- Calculated score for sword quality
video_azure_blob_url     -- For processed videos
velo_percentile_overall  -- Pitch percentiles
spin_percentile_pitch_type
bat_speed_percentile_sword
perceived_velocity       -- Based on release extension
strike_zone_distance_inches -- Distance from zone edge
sz_top, sz_bot          -- Strike zone boundaries
-- ... and more
```

## 🔧 Key Scripts

### 1. Data Collection
- **`download_full_2025_season.py`** - Downloads all MLB data from pybaseball
- **`get_play_ids_on_demand.py`** - Gets MLB play IDs for specific pitches

### 2. Database Setup
- **`create_mlb_enhanced_table.sql`** - Supabase table schema
- **`upload_data_correctly.py`** - Uploads data with proper type handling
- **`add_sz_columns.sql`** - Adds strike zone columns to existing table

### 3. Video Processing
- **`clean_video_processor.py`** - Downloads videos from MLB & uploads to Azure
- **`process_top_sword_videos.py`** - Complete video pipeline with Azure integration
- **`process_regular_season_videos_smart.py`** - Smart processor that skips completed dates

### 4. Data Calculations (Currently Running!)
- **`calculate_perceived_velocity.py`** - Calculates perceived velocity based on extension
- **`calculate_strike_zone_distance.py`** - Calculates distance from strike zone
- **`calculate_percentiles_sql.py`** - Fast SQL-based percentile calculator
- **`calculate_all_sword_scores.py`** - Calculate sword scores for entire database

### 5. Daily Operations
- **`daily_update.py`** - Automated daily data refresh with all calculations
- **`update_percentiles_daily.py`** - Efficient percentile updates using cached distributions

### 6. API Development
- **`api.py`** - FastAPI backend with initial endpoints
- **`setup_database_for_ui.py`** - Interactive database preparation script

## 🏗️ Setup From Scratch

### Prerequisites
```bash
# Python 3.9+
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Environment Variables (.env)
```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=postgresql://...

# Azure Blob Storage (for video hosting)
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_CONTAINER_NAME=swordfinder-videos
```

⚠️ **Note**: Copy `.env.example` to `.env` and fill in your credentials.

✅ **Status**: Both Supabase and Azure are now configured and tested!

### Step 1: Download MLB Data
```bash
python download_full_2025_season.py
# Creates: mlb_2025_full_season_complete.csv (227MB)
```

### Step 2: Create Database
1. Go to Supabase SQL editor
2. Run `create_mlb_enhanced_table.sql`
3. Creates table with indexes

### Step 3: Upload Data
```bash
python upload_data_correctly.py
# Uploads 353,501 pitches in ~3 minutes
```

### Step 4: Verify
```sql
-- In Supabase SQL editor
SELECT COUNT(*) FROM mlb_pitches_enhanced;
-- Should return 353,501
```

## 🎯 Finding Sword Swings

### SQL Queries
```sql
-- Worst sword swings
SELECT player_name, bat_speed, release_speed, sword_score, game_date
FROM mlb_pitches_enhanced
WHERE bat_speed < 30 AND bat_speed > 0
ORDER BY bat_speed ASC
LIMIT 10;

-- True sword swings (all criteria)
SELECT *
FROM mlb_pitches_enhanced
WHERE strikes = 2 
  AND events = 'strikeout'
  AND description IN ('swinging_strike', 'swinging_strike_blocked')
  AND bat_speed < 60
  AND swing_path_tilt > 30
ORDER BY bat_speed ASC;
```

### Python Example
```python
import pandas as pd
from supabase import create_client

# Connect
supabase = create_client(url, key)

# Query worst swords
result = supabase.table('mlb_pitches_enhanced')\
    .select('*')\
    .lt('bat_speed', 30)\
    .gt('bat_speed', 0)\
    .order('bat_speed')\
    .limit(10)\
    .execute()

# Get play IDs and download videos
from get_play_ids_on_demand import get_play_ids_for_pitches, download_video

df = pd.DataFrame(result.data)
df_with_ids = get_play_ids_for_pitches(df)

for _, pitch in df_with_ids.iterrows():
    if pitch['mlb_play_id']:
        download_video(pitch['mlb_play_id'], f"sword_{pitch['player_name']}.mp4")
```

## 📹 Video Processing

### Get Videos for Any Query
```python
# 1. Query your data
longest_hrs = supabase.table('mlb_pitches_enhanced')\
    .select('*')\
    .eq('is_home_run', True)\
    .order('hit_distance_sc', desc=True)\
    .limit(10)\
    .execute()

# 2. Get play IDs (only when needed)
df = pd.DataFrame(longest_hrs.data)
df_with_ids = get_play_ids_for_pitches(df)

# 3. Download videos
for _, hr in df_with_ids.iterrows():
    download_video(hr['mlb_play_id'], f"HR_{hr['hit_distance_sc']}ft.mp4")
```

## 🔄 Daily Updates (New!)

Keep your data fresh with automated daily updates:

```bash
# Test the daily update script
python daily_update.py

# Schedule it to run at 1pm daily
# See setup_daily_update.md for options (cron, GitHub Actions, etc.)
```

The script will:
- Fetch yesterday's MLB data (~3,000 pitches)
- Calculate sword scores
- Insert into Supabase (handles duplicates)
- **Calculate percentiles for the new data** 🆕
- Log the top sword swings
- Takes ~2 minutes to run

### How Daily Percentiles Work

Instead of recalculating ALL percentiles (slow), the daily update:
1. **Uses cached distributions** - Stores percentile breakpoints (1st, 5th, 10th, etc.)
2. **Interpolates new values** - Estimates percentiles based on where they fall
3. **Refreshes weekly** - Rebuilds the cache to stay accurate
4. **Runs automatically** - Integrated into `daily_update.py`

This approach is ~100x faster than recalculating everything!

## 📏 Extension & Perceived Velocity

Release extension dramatically affects how hitters perceive velocity:

### The Math
```
Perceived Velocity = Actual Velocity × (60.5 / (60.5 - Extension))
```

Example: **95 mph with 7 feet of extension**
- Effective distance: 60.5 - 7 = 53.5 feet
- Perceived velocity: 95 × (60.5/53.5) = **107.4 mph**
- That's a **+12.4 mph gain** from extension alone!

### Calculate for Your Database
```bash
python calculate_perceived_velocity.py
# Currently running - 5.8% complete, ETA: 10-12 hours
```

### New Percentiles Available
- **Extension percentiles**: How does a pitcher's extension compare?
- **Perceived velocity percentiles**: The velocity hitters actually experience

### Sample Queries
```sql
-- Find pitchers with elite extension
SELECT pitcher_name, AVG(release_extension) as avg_extension,
       AVG(extension_percentile_overall) as extension_pct
FROM mlb_pitches_enhanced
WHERE release_extension IS NOT NULL
GROUP BY pitcher_name
HAVING COUNT(*) > 100
ORDER BY avg_extension DESC
LIMIT 10;

-- Biggest perceived velocity gains
SELECT pitcher_name, pitch_type, release_speed, release_extension,
       perceived_velocity, (perceived_velocity - release_speed) as velo_gain
FROM mlb_pitches_enhanced
WHERE perceived_velocity IS NOT NULL
ORDER BY velo_gain DESC
LIMIT 20;
```

## 🔍 Key Discoveries

1. **Play ID Mapping**: Each pitch needs the LAST play ID from its at-bat
2. **Data Integrity**: Only ~10% of "sword candidates" are true sword swings
3. **Bat Tracking**: Available for ~44% of all pitches in 2025
4. **Spring Training Videos**: Spring training games (game_type = 'S') do NOT have video coverage!
   - Only regular season games (game_type = 'R') have videos
   - Use `process_regular_season_videos.py` to skip spring training automatically

## 📈 Next Steps

📋 **See TODO.md for the complete post-video roadmap!**

1. **Set Up Daily Updates** ✨
   - Run `python daily_update.py` to test
   - Follow `setup_daily_update.md` to schedule
   - Keeps your data fresh automatically

2. **Calculate Percentiles** ✨
   - First, run `create_percentile_functions.sql` in Supabase SQL Editor
   - Then run `python calculate_percentiles_sql.py` for fast SQL-based calculation
   - Or use `python calculate_percentiles.py` for Python version
   - Calculates velocity, spin, movement, and bat speed percentiles
   - Daily updates will handle percentiles automatically after this!
   - See `percentile_calculation_plan.md` for details

3. **Process Videos**
   - Run `process_top_sword_videos.py` for top 100 swords
   - Upload to Azure Blob Storage
   - Update video_azure_blob_url in database

4. **Build API**
   - FastAPI with endpoints for queries
   - Video streaming from Azure CDN
   - Real-time updates via Supabase

5. **Frontend**
   - Next.js app with video player
   - Leaderboards and statistics
   - Search and filter interface

## 📁 Project Structure

The project has been cleaned up to maintain only essential production files:

### Core Documentation
- **README.md** - This documentation
- **requirements.txt** - Python dependencies
- **TODO.md** - Comprehensive roadmap (updated June 22, 2024)

### Data Files
- **mlb_2025_full_season_complete.csv** - Complete 2025 MLB data (227MB)
- **mlb_2025_with_sword_scores.csv** - MLB data with calculated sword scores (232MB)

### Processing Scripts
- Data collection and upload scripts
- Video processing and Azure upload scripts
- Calculation scripts for perceived velocity, strike zone distance, and percentiles
- Daily update automation

### API & UI Development
- **api.py** - FastAPI backend with endpoints
- **QUICK_START_UI.md** - Step-by-step UI building guide
- Database setup and migration scripts

### Legacy Reference
The `legacy/` directory contains the original Flask app for reference

### Support Files
- Configuration and planning documents
- SQL scripts for database operations
- Testing scripts for specific dates/scenarios

## 📊 Sample Results

### Slowest Bat Speeds (2025)
1. Gunnar Hoglund - 15.3 mph
2. Trevor Williams - 15.4 mph
3. Charlie Morton - 15.4 mph

### Longest Home Runs (2025)
1. Landen Roupp - 484 ft
2. Jack Leiter - 479 ft
3. JP Sears - 470 ft

### Fastest Pitches (2025)
1. Mason Miller - 103.9 mph
2. Aroldis Chapman - 103.8 mph
3. Mason Miller - 103.7 mph

## 🆘 Troubleshooting

### Import Errors
- Check data types match schema
- Ensure no infinity/NaN values
- Verify column names match

### Video Download Issues
- Confirm play_id is valid
- Check MLB video availability
- Some games may not have video

### Performance
- Use indexes for common queries
- Batch operations when possible
- Consider partitioning by date

## 📝 License

This project uses publicly available MLB data. Video content belongs to MLB.

---

**Created**: January 2025  
**Last Updated**: June 22, 2024, 4:00 PM PST
**Status**: Background calculations in progress (ETA: 10-12 hours)
**Next Steps**: Complete calculations, then build frontend UI 