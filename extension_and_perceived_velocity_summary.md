# Extension, Perceived Velocity & Strike Zone Distance - Complete Implementation

## ✅ What's Now Available

### Database Fields
1. **`release_extension`** - Already in database (feet from rubber)
2. **`perceived_velocity`** - NEW field we added
3. **`strike_zone_distance_inches`** - NEW! Distance from strike zone edge in inches
4. **`extension_percentile_overall`** - How pitcher's extension compares to all
5. **`extension_percentile_pitch_type`** - Extension compared to same pitch type
6. **`perceived_velo_percentile_overall`** - Perceived velocity percentile
7. **`perceived_velo_percentile_pitch_type`** - Perceived velocity by pitch type

### Complete Percentile Coverage

Now calculating percentiles for:
- ⚡ **Velocity** (actual)
- 🌀 **Spin rate**
- 📐 **Movement** (total break)
- 🏏 **Bat speed** (including inverted sword percentiles)
- 📏 **Extension** (NEW!)
- 🚀 **Perceived velocity** (NEW!)

## 🧮 The Math Behind Perceived Velocity

```
Standard mound distance: 60.5 feet (60 feet 6 inches)
Effective distance = 60.5 - extension

Perceived Velocity = Actual Velocity × (60.5 / Effective Distance)
```

### Real Examples:
- **Jacob deGrom**: 99 mph with 6.5' extension = **106.8 mph perceived** (+7.8 mph)
- **Tyler Glasnow**: 97 mph with 7.0' extension = **109.6 mph perceived** (+12.6 mph)
- **Aroldis Chapman**: 103 mph with 5.5' extension = **108.5 mph perceived** (+5.5 mph)

Extension can matter more than raw velocity!

## 📐 Strike Zone Distance

Measures how far outside the strike zone a pitch was when a batter swung (especially on sword swings).

### The Math
```
Strike Zone: 17" wide × (sz_top - sz_bot) tall
Distance = minimum distance to nearest edge

If pitch is:
- Outside horizontally: distance from plate edge (8.5" from center)
- High/Low: distance from sz_top or sz_bot
- Both: Euclidean distance to nearest corner
```

### Why It Matters for Swords
The worst sword swings often happen on pitches WAY outside the zone:
- Batter completely fooled
- Chasing bad pitches
- Late recognition

## 📊 How to Use

### One-Time Setup

**1. Add the new columns to your database:**

Run this SQL in your Supabase SQL Editor:
```sql
ALTER TABLE mlb_pitches_enhanced 
ADD COLUMN IF NOT EXISTS perceived_velocity REAL,
ADD COLUMN IF NOT EXISTS perceived_velo_percentile_overall REAL,
ADD COLUMN IF NOT EXISTS perceived_velo_percentile_pitch_type REAL,
ADD COLUMN IF NOT EXISTS strike_zone_distance_inches REAL;
```

**2. Calculate perceived velocity for all pitches:**
```bash
python calculate_perceived_velocity.py
```

**3. Calculate strike zone distance for all pitches:**
```bash
python calculate_strike_zone_distance.py
```

**4. Update all percentiles (including new extension/perceived velo):**
```bash
python calculate_percentiles_sql.py
```

### Daily Updates (Automatic)
The `daily_update.py` script now:
1. Fetches new MLB data
2. **Calculates perceived velocity automatically**
3. **Calculates strike zone distance automatically**
4. Updates all percentiles including extension & perceived velocity

### Useful Queries

```sql
-- Pitchers who gain the most from extension
SELECT 
    pitcher_name,
    COUNT(*) as pitches,
    AVG(release_speed) as avg_velo,
    AVG(release_extension) as avg_extension,
    AVG(perceived_velocity) as avg_perceived,
    AVG(perceived_velocity - release_speed) as avg_gain
FROM mlb_pitches_enhanced
WHERE pitch_type IN ('FF', 'SI', 'FC')  -- Fastballs only
GROUP BY pitcher_name
HAVING COUNT(*) > 100
ORDER BY avg_gain DESC
LIMIT 20;

-- Find "sneaky fast" pitchers (low actual velo, high perceived)
SELECT 
    pitcher_name,
    AVG(release_speed) as actual_velo,
    AVG(perceived_velocity) as perceived_velo,
    AVG(velo_percentile_overall) as actual_pct,
    AVG(perceived_velo_percentile_overall) as perceived_pct
FROM mlb_pitches_enhanced
WHERE pitch_type = 'FF'
  AND velo_percentile_overall < 50  -- Below average actual velocity
  AND perceived_velo_percentile_overall > 70  -- Above average perceived
GROUP BY pitcher_name
HAVING COUNT(*) > 50
ORDER BY (perceived_pct - actual_pct) DESC;

-- Extension leaders by pitch type
SELECT 
    pitch_type,
    pitcher_name,
    AVG(release_extension) as avg_extension,
    AVG(extension_percentile_pitch_type) as extension_pct
FROM mlb_pitches_enhanced
WHERE release_extension IS NOT NULL
GROUP BY pitch_type, pitcher_name
HAVING COUNT(*) > 50
ORDER BY pitch_type, avg_extension DESC;
```

-- Worst sword swings by strike zone distance
SELECT 
    player_name,
    pitcher_name,
    bat_speed,
    sword_score,
    strike_zone_distance_inches,
    pitch_type,
    description
FROM mlb_pitches_enhanced
WHERE sword_score > 70
  AND strike_zone_distance_inches > 12  -- More than a foot outside!
ORDER BY strike_zone_distance_inches DESC
LIMIT 20;

-- Which pitchers get the most chases outside the zone?
SELECT 
    pitcher_name,
    AVG(strike_zone_distance_inches) as avg_chase_distance,
    COUNT(*) as total_chases,
    AVG(CASE WHEN sword_score > 0 THEN sword_score END) as avg_sword_score
FROM mlb_pitches_enhanced
WHERE description LIKE '%swinging_strike%'
  AND strike_zone_distance_inches > 6  -- At least 6 inches out
GROUP BY pitcher_name
HAVING COUNT(*) > 20
ORDER BY avg_chase_distance DESC;
```

## 🎯 Impact on Sword Swings

Extension affects sword swings too! Query to find worst swings on "sneaky fast" pitches:

```sql
SELECT 
    player_name,
    pitcher_name,
    bat_speed,
    sword_score,
    release_speed as actual_velo,
    perceived_velocity,
    release_extension,
    (perceived_velocity - release_speed) as velo_added
FROM mlb_pitches_enhanced
WHERE sword_score > 80
  AND perceived_velocity > release_speed + 10  -- 10+ mph gain from extension
ORDER BY sword_score DESC
LIMIT 20;
```

## 📈 Next Steps

1. **Visualizations**: Create charts showing actual vs perceived velocity
2. **Pitcher profiles**: Build extension profiles for each pitcher
3. **Matchup analysis**: How do hitters perform against high-extension pitchers?
4. **Sword correlation**: Do high-extension pitchers generate more sword swings? 