<p align="center">
  <img src="static/logo.png" alt="Product Demo" width="250"/>
</p>

<h1 align="center">SwordFinder ⚔️</h1>


A sophisticated Flask API that leverages MLB Statcast data to analyze and score baseball "sword swings" using advanced computational techniques and custom algorithms.

## Overview

SwordFinder identifies and analyzes the most impressive baseball swings that result in swinging strikes - these are called "sword swings" because the batter "swings and misses" at difficult pitches. The system uses authentic MLB Statcast data to find, score, and rank the top sword swings with comprehensive analysis including percentile rankings, expert AI commentary, and video highlights.

## Key Features

- **Authentic MLB Data**: Uses 226,833+ real Statcast records from official MLB sources
- **Advanced Filtering**: Identifies sword swings using multiple swing mechanics criteria
- **Custom Scoring Algorithm**: Proprietary weighted formula scoring swings 50-100 points
- **Percentile Analysis**: Compares each swing against entire season's data
- **AI Expert Commentary**: Claude-powered analysis of what makes each swing special
- **Video Integration**: Direct links to Baseball Savant video highlights and embedded MP4s.
- **Database Caching**: Supabase (PostgreSQL) storage for fast response times.
- **Live Patch System**: Browser-based tool to update missing data.
- **Dynamic Dashboards**:
    - Top 5 Swords by selected date.
    - Top 5 Swords of 2025 (All-Time) displayed on the main page, ranked by `raw_sword_metric`.

## Technical Architecture

### Backend Stack
- **Python 3.11** - Core runtime
- **Flask** - Web framework and API endpoints
- **Supabase (PostgreSQL)** - Primary database with 118+ Statcast fields
- **SQLAlchemy** - Database ORM and query optimization
- **Azure Blob Storage** - Video file storage and content delivery
- **pybaseball** - Official MLB data source integration
- **pandas** - Data processing and analysis
- **NumPy** - Statistical calculations and percentile ranking

### Data Sources
- **MLB Statcast**: Official pitch-by-pitch data via pybaseball
- **Baseball Savant**: Video highlights and play details
- **MLB Stats API**: Game data and player information

### Cloud Infrastructure
- **Supabase**: Managed PostgreSQL database with real-time capabilities
  - Hosts all MLB Statcast data (226,833+ records)
  - Manages user authentication and row-level security
  - Provides real-time subscriptions for live updates
- **Azure Blob Storage**: Scalable object storage for video files
  - Stores downloaded MP4 video clips
  - Provides fast global content delivery
  - Handles large file uploads and streaming

### Core Components

#### 1. Sword Swing Detection Engine
**File**: `simple_db_swordfinder.py`

**Critical Rule**: A true sword swing is the **final pitch of an at-bat that results in a strikeout**, where that final pitch is a `swinging_strike` or `swinging_strike_blocked`.

**Filtering Criteria (Conceptual - implemented in Python after SQL fetch):**
- **Bat Speed**: Preferably less than 60 mph (slower swings indicate difficulty).
- **Intercept Y**: Preferably greater than 14 inches (swing path intersection).
- **Swing Path Tilt**: Preferably greater than 30 degrees (steep swing angle).
- **Zone Penalty**: Dynamically calculated based on pitch location relative to strike zone.

**Query Logic (in `simple_db_swordfinder.py`):**
1.  A CTE (`final_pitches_of_strikeout_at_bats`) uses `DISTINCT ON (game_pk, at_bat_number)` and `ORDER BY ... pitch_number DESC` to select the *last recorded pitch* of all at-bats on a given date where `events = 'strikeout'`.
2.  The main query then selects from this CTE, further filtering these last pitches for `description IN ('swinging_strike', 'swinging_strike_blocked')`.
3.  It also ensures `bat_speed`, `swing_path_tilt`, and `intercept_ball_minus_batter_pos_y_inches` (aliased as `intercept_y`) are `NOT NULL`.
4.  All such candidates are returned to Python.

**Scoring Logic (in `simple_db_swordfinder.py`):**
1.  **Dynamic Zone Penalty Factor:** Calculated for each candidate based on `plate_x`, `plate_z`, `sz_top`, `sz_bot`. A factor >= 1.0 (1.0 is neutral, >1.0 rewards pitches further from the zone).
    ```python
    # Simplified concept from _calculate_dynamic_zone_penalty:
    out_x_feet = max(abs(plate_x) - 0.83, 0)
    # ... calculation for out_z_feet ...
    penalty_inches = (out_x_feet + out_z_feet) * 12
    scaled_bonus = min(penalty_inches / 18.0, 2.0) 
    dynamic_zone_penalty_factor = 1.0 + scaled_bonus
    ```
2.  **Raw Sword Metric:** Calculated for each candidate:
    ```python
    # Components are normalized (0-1 range, higher is "better" for a sword)
    bat_speed_comp = (60 - bat_speed) / 60 # if bat_speed <= 60 else 0
    tilt_comp = swing_path_tilt / 60 # if swing_path_tilt <= 60 else 1.0
    intercept_comp = intercept_y / 50 # if intercept_y <= 50 else 1.0

    raw_sword_metric = (
        0.35 * bat_speed_comp +
        0.25 * tilt_comp +
        0.25 * intercept_comp +
        0.15 * dynamic_zone_penalty_factor 
    )
    ```
3.  **Sorting:** All candidates are sorted by `raw_sword_metric` in descending order.
4.  **Final Scores for Top 5:**
    *   `sword_score` (Universal Scale): `raw_sword_metric * 50 + 50`
    *   `daily_normalized_score` (Daily UX Scale): Min-max normalized against all of the day's `raw_sword_metric` values, then scaled `50 + normalized_value * 50`.
    *   Both scores, plus `raw_sword_metric`, are included in the API response for the top 5 swords.

#### 2. Database Schema
**File**: `models_complete.py`

**Primary Table**: `statcast_pitches`
- 118+ fields covering all MLB Statcast data
- Optimized indexes on game_date, player_name, pitch_type
- Complete pitch details: velocity, spin rate, location, teams

**Note on Player Names and IDs**:
- **Pitcher Name**: For each pitch event, the pitcher's name is sourced from the `player_name` field in the `statcast_pitches` table. The `pitcher` field contains the pitcher's MLBAM ID.
- **Batter Name**: The batter's name is not directly available in the `statcast_pitches` table for each pitch. It is fetched dynamically by the application (`simple_db_swordfinder.py`) using the `batter` field (batter's MLBAM ID) to query the MLB Stats API (`https://statsapi.mlb.com/api/v1/people/{batter_id}`).
- **Pitch Name**: This refers to the descriptive name of the pitch type (e.g., "4-Seam Fastball") and is sourced from the `pitch_name` field in `statcast_pitches`. The `pitch_type` field contains the code (e.g., "FF").

**Analysis Table**: `sword_swings`
- Sword score calculations and rankings
- Percentile analysis results
- AI expert commentary
- Video URLs and Azure Blob Storage paths
- Cached results for performance

**Tracking Table**: `daily_results`
- Processing status by date
- Performance metrics and completion tracking

#### 3. Percentile Analysis Engine
**File**: `percentile_analyzer.py`

Compares each sword swing against season-wide data:
- **Bat Speed Percentile**: How slow compared to all swings
- **Swing Tilt Percentile**: How steep the swing angle
- **Velocity Percentile**: How fast the pitch was
- **Spin Rate Percentile**: How much the ball spun
- **Location Percentile**: Where in strike zone

#### 4. Expert AI Analysis
**Integration**: Claude Sonnet 4.0 via Anthropic API

Generates detailed commentary explaining:
- What made the swing technically difficult
- Pitch characteristics that created the challenge
- Swing mechanics analysis
- Context within the at-bat situation

## Recent Updates (May 26, 2025)

### 1. Fixed Sword Query Logic
- **Issue**: Query was returning no results due to overly restrictive filters
- **Solution**: Modified query to use CTE (Common Table Expression) to first identify strikeout at-bats, then find swinging strikes within those at-bats
- **Files Modified**: `simple_db_swordfinder.py`

### 2. Database Field Mapping Corrections & Batter Name Lookup
- **Issue**: Original field index mappings were incorrect in `simple_db_swordfinder.py`, leading to data misalignment (e.g., descriptive pitch names appearing in `batter_id` field, `pfx_z` values in `pitch_name` field). Batter names were also not being displayed.
- **Solution**:
    - Corrected field index mappings in `simple_db_swordfinder.py` to accurately reflect the SQL query's column order.
    - Implemented dynamic fetching of batter names using the `batter` ID (MLBAM ID) and the MLB Stats API (`https://statsapi.mlb.com/api/v1/people/{batter_id}`).
- **Current Status**: API now correctly returns sword swings with proper field values, including pitcher names, fetched batter names, and correct descriptive pitch names.
- **Note on `launch_angle` and `launch_speed`**: These fields will typically be `null` for sword swings (which are swinging strikes) because no ball is put into play. This is expected behavior and not a mapping error.

### 3. Diagnostic Tools Created
- **test_query.py**: Diagnostic script to check database contents and validate queries
- **debug_swords.py**: Comprehensive debugging tool for sword swing detection
- **Purpose**: Help identify why queries return empty results and validate data presence

### 4. Validated Data Presence
- **Confirmed**: Database has 4,650 pitches for May 24, 2025
- **Swinging Strikes**: 470 total swinging strikes on that date
- **With Bat Speed Data**: 468 swinging strikes have bat speed data
- **In Strikeout At-Bats**: 287 swinging strikes are part of strikeout at-bats

## Infrastructure Migration Status

### Current Production Setup
- ✅ **Database**: Supabase (PostgreSQL) - Fully configured and operational
- ✅ **Video Storage**: Azure Blob Storage - Ready for integration
- ⚠️ **Code Migration**: In progress - Some files still contain local development configurations

### Working Features  
- ✅ Database connection and query execution
- ✅ Sword swing detection for strikeout at-bats
- ✅ API returns 5 sword swings for May 24, 2025
- ✅ Video URL generation and Azure Blob Storage integration
- ✅ Basic scoring algorithm implementation

### Migration TODO
- 🔄 Update hardcoded local database URLs in Python files to use Supabase
- 🔄 Replace local `static/videos` storage with Azure Blob Storage integration
- 🔄 Add Azure Storage SDK implementation for video upload/download
- 🔄 Update environment variable handling across all modules

### Known Issues
1. **Field Mapping**: (Addressed) Previous issues with `pitch_name` and `batter_id` have been corrected.
   
2. **Missing pitcher_name**: (Addressed) Pitcher names are sourced from the `player_name` field for pitch events. Batter names are now fetched via API.

3. **Video URLs**: Generated URLs may not always work
   - Some playIds might be invalid
   - Need better error handling for missing videos

## Next Steps for Development

### Immediate Priorities (Next Developer Should Start Here)

(The following items were the original priorities and have now been addressed by the updates on May 26, 2025)

#### 1. Fix Field Mapping Issues (✅ Addressed)
- Field mappings in `simple_db_swordfinder.py` have been corrected.
- Batter names are now fetched and included.

#### 2. Add Pitcher Name Support (✅ Addressed)
- Pitcher names are correctly sourced from `player_name`.
- Batter names are fetched via API.

#### 3. Improve Video Integration
- Add error handling for missing/invalid playIds
- Implement retry logic for failed video downloads
- Optimize Azure Blob Storage for video delivery and CDN integration
- Consider caching video metadata in Supabase

#### 4. Enhance Sword Criteria
- Consider adding more sophisticated criteria
- Weight factors based on statistical analysis
- Add machine learning model for sword prediction
- Include exit velocity and launch angle when available

### Medium-Term Goals

#### 1. Complete Azure Blob Storage Integration
- Replace local file storage with Azure Blob Storage SDK
- Implement video upload/download with proper error handling
- Add video streaming capabilities for large files
- Set up CDN integration for global video delivery
- Implement automatic video transcoding for different quality levels

#### 2. Performance Optimization
- Add Redis caching for frequent queries
- Implement query result pagination
- Leverage Supabase's built-in query optimization and indexing
- Utilize Supabase Edge Functions for compute-heavy operations
- Add database connection pooling

#### 3. Data Quality Improvements
- Implement data validation on import
- Add data completeness checks
- Create automated tests for data integrity
- Build data quality dashboard

#### 4. API Enhancements
- Add date range queries (not just single date)
- Implement player-specific sword queries
- Add team-based filtering
- Create aggregate statistics endpoints
- New endpoint `/api/top-swords-2025` provides data for the all-time 2025 leaderboard.

#### 5. Frontend Development
- **Main Page (`home.html`)**:
    - Displays top 5 swords for a user-selected date.
    - Features a "Top 5 Swords of 2025 (All-Time)" dashboard that loads automatically, showing swords ranked by `raw_sword_metric` with embedded videos.
- Add video player with swing analysis overlay (partially done with basic player).
- Create interactive charts for sword metrics.
- Implement real-time updates during games.

### Long-Term Vision

#### 1. Machine Learning Integration
- Train model to predict sword swings
- Identify patterns in sword-prone situations
- Create pitcher-batter matchup analysis
- Build predictive sword scoring

#### 2. Real-Time Processing
- Connect to live MLB data feeds
- Process swings as they happen
- Send notifications for epic swords
- Build live leaderboards

#### 3. Advanced Analytics
- Compare sword rates across eras
- Analyze sword trends by ballpark
- Study impact of weather on swords
- Create sword difficulty rankings

#### 4. Mobile Application
- Native iOS/Android apps
- Push notifications for favorite players
- Offline video viewing
- Social sharing features

## Testing & Validation

### Current Test Coverage
- Database connectivity tests
- Query result validation
- Field mapping verification
- API endpoint testing

### Recommended Test Suite
```bash
# Run diagnostic tests
python test_query.py          # Database query testing
python debug_swords.py        # Sword detection validation
python test_percentiles.py    # Percentile calculation tests

# API testing
curl -X POST http://localhost:5001/swords \
  -H "Content-Type: application/json" \
  -d '{"date": "2025-05-24"}' | jq '.'
```

### Data Validation Queries
```sql
-- Check strikeout at-bats
SELECT COUNT(DISTINCT CONCAT(game_pk, '-', at_bat_number))
FROM statcast_pitches 
WHERE game_date = '2025-05-24'
AND events = 'strikeout';

-- Verify sword candidates
WITH strikeout_at_bats AS (
    SELECT DISTINCT game_pk, at_bat_number
    FROM statcast_pitches
    WHERE game_date = '2025-05-24'
    AND events = 'strikeout'
)
SELECT COUNT(*)
FROM statcast_pitches sp
JOIN strikeout_at_bats sa 
    ON sp.game_pk = sa.game_pk 
    AND sp.at_bat_number = sa.at_bat_number
WHERE sp.game_date = '2025-05-24'
AND sp.description IN ('swinging_strike', 'swinging_strike_blocked')
AND sp.bat_speed IS NOT NULL;
```

## Development Environment Setup

### Required Environment Variables
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
DATABASE_URL=postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres
AZURE_STORAGE_ACCOUNT=your-storage-account-name
AZURE_STORAGE_KEY=your-storage-account-key
AZURE_CONTAINER_NAME=swordfinder-videos
SESSION_SECRET=your-flask-session-secret
ANTHROPIC_API_KEY=your-anthropic-api-key  # Optional for AI analysis
```

### Local Development Commands
```bash
# Start Flask development server
cd SwordFinder
source venv/bin/activate
export DATABASE_URL="postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres"
export AZURE_STORAGE_ACCOUNT="your-storage-account-name"
export AZURE_STORAGE_KEY="your-storage-account-key"
python app.py

# Run diagnostic tools
python test_query.py
python debug_swords.py

# Test API endpoints
curl -X POST http://localhost:5001/swords -H "Content-Type: application/json" -d '{"date": "2025-05-24"}'
```

## Troubleshooting Guide

### Issue: API Returns Empty Results
1. Check if date has data: `python test_query.py`
2. Verify strikeouts exist for that date
3. Confirm swinging strikes have bat speed data
4. Check query filters aren't too restrictive

### Issue: Field Values Appear Incorrect
1. Print raw query results to verify field order
2. Check field index mappings in sword_swing dictionary
3. Verify database schema matches expected fields
4. Use debug_swords.py to inspect actual data

### Issue: Database Connection Errors
1. Verify Supabase project is active and accessible
2. Check DATABASE_URL and Supabase credentials are set correctly
3. Confirm database tables exist in Supabase dashboard
4. Test connection with Supabase SQL editor or psql client

### Issue: Video Downloads Fail
1. Check if play_id/sv_id is valid
2. Verify Baseball Savant URL format
3. Check network connectivity
4. Review video_downloader.py logs

### Issue: Azure Blob Storage Errors
1. Verify Azure Storage Account credentials are correct
2. Check AZURE_STORAGE_ACCOUNT and AZURE_STORAGE_KEY environment variables
3. Confirm storage container exists and has proper permissions
4. Test blob upload/download with Azure Storage Explorer
5. Check Azure Storage account quotas and billing status

## Contributing

### Code Style
- Follow PEP 8 Python style guidelines
- Use type hints where appropriate
- Include comprehensive docstrings
- Add unit tests for new features

### Pull Request Process
1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Update documentation
5. Submit pull request with detailed description

### Development Best Practices
- Always test with real MLB data
- Validate sword criteria changes with domain experts
- Document any field mapping changes
- Keep backwards compatibility for API endpoints

## License

This project uses authentic MLB data through official APIs and adheres to all terms of service for data usage.

## Support

For technical issues or questions:
1. Check troubleshooting section
2. Review application logs
3. Use built-in diagnostic tools
4. Consult API documentation

---

**SwordFinder** - Cutting through baseball data to find the sharpest swings ⚔️
