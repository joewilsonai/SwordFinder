# Percentile Calculation Plan for SwordFinder

## Overview
Calculate percentiles for various pitch and swing metrics to provide context for how extreme each pitch/swing is compared to the overall population.

## Database Fields to Populate

### 1. Velocity Percentiles
- **`velo_percentile_overall`**: How fast is this pitch compared to ALL pitches?
- **`velo_percentile_pitch_type`**: How fast is this pitch compared to same pitch type?
  - Example: 95 mph fastball = 50th percentile for fastballs, but 90th percentile overall

### 2. Spin Rate Percentiles  
- **`spin_percentile_overall`**: Spin rate compared to ALL pitches
- **`spin_percentile_pitch_type`**: Spin rate compared to same pitch type
  - Example: 2500 rpm slider = 80th percentile for sliders

### 3. Movement Percentiles
- **`movement_percentile_overall`**: Total movement compared to ALL pitches
- **`movement_percentile_pitch_type`**: Movement compared to same pitch type
  - Calculate using: `sqrt(pfx_x^2 + pfx_z^2)` for total movement

### 4. Bat Speed Percentiles
- **`bat_speed_percentile_overall`**: Bat speed compared to ALL swings
- **`bat_speed_percentile_sword`**: Bat speed compared to ONLY sword swings
  - This shows how bad a sword swing is even among other swords!

## Calculation Strategy

### Step 1: Build Distribution Tables
```sql
-- Create materialized views for performance
CREATE MATERIALIZED VIEW pitch_velo_distribution AS
SELECT 
    pitch_type,
    PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY release_speed) as p1,
    PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY release_speed) as p5,
    PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY release_speed) as p10,
    -- ... continue for all percentiles
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY release_speed) as p95,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY release_speed) as p99
FROM mlb_pitches_enhanced
WHERE release_speed IS NOT NULL
GROUP BY pitch_type;
```

### Step 2: Create Percentile Functions
```python
def calculate_percentile_rank(value, distribution):
    """Calculate what percentile a value falls into"""
    return (distribution < value).sum() / len(distribution) * 100

def calculate_all_percentiles(df):
    """Calculate all percentiles for a batch of pitches"""
    
    # Overall distributions
    velo_dist_overall = df['release_speed'].dropna()
    spin_dist_overall = df['release_spin_rate'].dropna()
    
    # Calculate movement magnitude
    df['movement_total'] = np.sqrt(df['pfx_x']**2 + df['pfx_z']**2)
    movement_dist_overall = df['movement_total'].dropna()
    
    # Bat speed distributions
    bat_speed_dist_overall = df[df['bat_speed'] > 0]['bat_speed']
    bat_speed_dist_sword = df[(df['sword_score'] > 0) & (df['bat_speed'] > 0)]['bat_speed']
    
    # Calculate percentiles
    for idx, row in df.iterrows():
        # Velocity percentiles
        if pd.notna(row['release_speed']):
            df.at[idx, 'velo_percentile_overall'] = calculate_percentile_rank(
                row['release_speed'], velo_dist_overall
            )
            
            # Pitch type specific
            pitch_type_velos = df[df['pitch_type'] == row['pitch_type']]['release_speed'].dropna()
            df.at[idx, 'velo_percentile_pitch_type'] = calculate_percentile_rank(
                row['release_speed'], pitch_type_velos
            )
```

### Step 3: Batch Processing Implementation
```python
def update_percentiles_in_batches():
    """Process entire database in batches"""
    
    batch_size = 10000
    offset = 0
    
    while True:
        # Get batch
        batch = supabase.table('mlb_pitches_enhanced')\
            .select('*')\
            .range(offset, offset + batch_size - 1)\
            .execute()
        
        if not batch.data:
            break
            
        df = pd.DataFrame(batch.data)
        
        # Calculate percentiles
        df = calculate_all_percentiles(df)
        
        # Update database
        for _, row in df.iterrows():
            update_data = {
                'velo_percentile_overall': row.get('velo_percentile_overall'),
                'velo_percentile_pitch_type': row.get('velo_percentile_pitch_type'),
                'spin_percentile_overall': row.get('spin_percentile_overall'),
                'spin_percentile_pitch_type': row.get('spin_percentile_pitch_type'),
                'movement_percentile_overall': row.get('movement_percentile_overall'),
                'movement_percentile_pitch_type': row.get('movement_percentile_pitch_type'),
                'bat_speed_percentile_overall': row.get('bat_speed_percentile_overall'),
                'bat_speed_percentile_sword': row.get('bat_speed_percentile_sword')
            }
            
            supabase.table('mlb_pitches_enhanced')\
                .update(update_data)\
                .eq('id', row['id'])\
                .execute()
        
        offset += batch_size
```

## Special Considerations

### 1. Inverse Percentiles for Swords
For sword swings, LOWER bat speed = HIGHER percentile (worse):
```python
# For sword percentiles, invert the ranking
df['bat_speed_percentile_sword'] = 100 - calculate_percentile_rank(
    row['bat_speed'], bat_speed_dist_sword
)
```

### 2. Pitch Type Grouping
Some pitch types should be grouped:
- Group all fastballs (FF, SI, FC) for velocity comparisons
- Group all breaking balls (SL, CU, KC) for spin comparisons

### 3. Missing Data Handling
- Skip percentile calculation if base metric is NULL
- Don't calculate pitch-type percentiles if < 100 samples

### 4. Performance Optimization
- Pre-calculate distributions once per run
- Use numpy operations instead of loops where possible
- Consider using PostgreSQL window functions:

```sql
UPDATE mlb_pitches_enhanced
SET velo_percentile_overall = subquery.percentile
FROM (
    SELECT id,
           PERCENT_RANK() OVER (ORDER BY release_speed) * 100 as percentile
    FROM mlb_pitches_enhanced
    WHERE release_speed IS NOT NULL
) as subquery
WHERE mlb_pitches_enhanced.id = subquery.id;
```

## Useful Queries After Implementation

### Find Extreme Pitches
```sql
-- 99th percentile velocity fastballs
SELECT * FROM mlb_pitches_enhanced
WHERE pitch_type IN ('FF', 'SI') 
  AND velo_percentile_pitch_type > 99;

-- Nastiest breaking balls (high spin + movement)
SELECT * FROM mlb_pitches_enhanced
WHERE pitch_type IN ('SL', 'CU')
  AND spin_percentile_pitch_type > 90
  AND movement_percentile_pitch_type > 90;

-- Worst sword swings (bottom 1% bat speed among swords)
SELECT * FROM mlb_pitches_enhanced
WHERE bat_speed_percentile_sword < 1
ORDER BY bat_speed ASC;
```

## Implementation Order

1. **Velocity percentiles first** (most straightforward)
2. **Spin rate percentiles** (similar approach)
3. **Movement percentiles** (requires calculation)
4. **Bat speed percentiles** (smaller dataset, only swings)

## Testing Strategy

1. Calculate percentiles for one day first
2. Verify distributions look correct (plot histograms)
3. Spot check extreme values
4. Run full database update

## Expected Results

- ~350k pitches with velocity percentiles
- ~350k pitches with spin percentiles  
- ~150k swings with bat speed percentiles
- ~1,000 sword swings with sword-specific percentiles 