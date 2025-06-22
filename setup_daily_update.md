# Setting Up Daily MLB Data Updates

The `daily_update.py` script fetches yesterday's MLB data and adds it to your Supabase database. Here are several ways to schedule it to run daily at 1pm:

## Option 1: Local Cron Job (Mac/Linux)

Add to your crontab:
```bash
# Edit crontab
crontab -e

# Add this line (runs at 1pm daily)
0 13 * * * cd /Users/joewilson/pythonprojects/swordfinder/SwordFinder && /Users/joewilson/pythonprojects/swordfinder/.venv/bin/python daily_update.py >> /Users/joewilson/pythonprojects/swordfinder/SwordFinder/cron.log 2>&1
```

## Option 2: GitHub Actions (Free & Reliable) ✅ ALREADY CONFIGURED!

The workflow is already set up at `.github/workflows/daily-update.yml`!

**To activate it:**
1. Push your code to GitHub (see GITHUB_SETUP.md for instructions)
2. Go to your GitHub repo Settings → Secrets and variables → Actions
3. Add these secrets:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY` (if needed)
   - `DATABASE_URL`
   - `AZURE_STORAGE_CONNECTION_STRING`
   - `AZURE_CONTAINER_NAME`
4. The workflow will run automatically at 1pm UTC daily
5. You can also trigger it manually from the Actions tab

**Features included:**
- Automatic daily runs at 1pm UTC
- Manual trigger option
- Log artifact storage (7 days)
- Failure notifications
- Dependency caching for faster runs

## Option 3: Supabase Edge Functions (Serverless)

Create a Supabase Edge Function that runs on a schedule:

```typescript
// supabase/functions/daily-mlb-update/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

serve(async (req) => {
  // Call your Python script via an API endpoint
  // Or rewrite the logic in TypeScript
  
  return new Response("Update completed", { status: 200 })
})
```

Then schedule it in Supabase Dashboard → Functions → Schedules.

## Option 4: Cloud Scheduler (Google Cloud/AWS)

### Google Cloud Scheduler:
```bash
# Create a Cloud Function that runs your Python script
gcloud scheduler jobs create http daily-mlb-update \
  --schedule="0 13 * * *" \
  --uri="YOUR_CLOUD_FUNCTION_URL" \
  --time-zone="America/New_York"
```

### AWS EventBridge + Lambda:
```python
# Lambda function that triggers daily
import subprocess
import boto3

def lambda_handler(event, context):
    # Run your update logic
    return {'statusCode': 200}
```

## Option 5: Simple Python Scheduler (Always Running)

Create `scheduler.py`:
```python
import schedule
import time
import subprocess
from datetime import datetime

def run_daily_update():
    print(f"Running daily update at {datetime.now()}")
    subprocess.run(["python", "daily_update.py"])

# Schedule for 1pm
schedule.every().day.at("13:00").do(run_daily_update)

print("Scheduler started. Waiting for 1pm daily...")
while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute
```

Run with: `nohup python scheduler.py &`

## Testing the Script

Before scheduling, test manually:
```bash
cd /Users/joewilson/pythonprojects/swordfinder/SwordFinder
python daily_update.py
```

Check `daily_update.log` for results.

## Monitoring

The script creates logs in `daily_update.log`. You can monitor:
- Success/failure status
- Number of pitches added
- Top sword swings found
- Any errors

## Handling Duplicates

The current implementation assumes you're adding yesterday's data once per day, so duplicates are unlikely. If you need to handle re-runs or duplicates:

1. Add `sv_id` column to your table:
   ```sql
   ALTER TABLE mlb_pitches_enhanced ADD COLUMN sv_id TEXT;
   CREATE UNIQUE INDEX idx_sv_id_unique ON mlb_pitches_enhanced(sv_id);
   ```

2. Or create a composite unique constraint:
   ```sql
   ALTER TABLE mlb_pitches_enhanced 
   ADD CONSTRAINT unique_pitch 
   UNIQUE (game_pk, at_bat_number, pitch_number);
   ```

Then update the daily_update.py to use `upsert()` instead of `insert()`.

## Recommended Approach

For reliability and zero maintenance, **GitHub Actions** (Option 2) is recommended because:
- Free for public repos (or 2000 minutes/month for private)
- No server needed
- Built-in secret management
- Easy to monitor and debug
- Automatic notifications on failure 