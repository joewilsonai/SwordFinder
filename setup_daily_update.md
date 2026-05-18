# Daily Update Operations

The daily update is handled by GitHub Actions.

## Workflow Order

1. `Daily MLB Data Update`
   - Fetches yesterday's Statcast data.
   - Calculates sword candidates and scores.
   - Uploads new rows to Supabase.
   - Updates daily percentile fields.

2. `Process Daily Sword Videos`
   - Runs only after the daily update workflow succeeds, or by manual dispatch.
   - Finds the top sword candidates for the target date.
   - Fetches MLB play IDs, downloads clips, uploads to Azure Blob, and updates Supabase.

3. `Production Smoke Check`
   - Checks Railway API health and live data.
   - Checks the core Vercel UI routes.

## Local Dry Checks

```bash
cd /Users/joewilson/pythonprojects/swordfinder/SwordFinder
source .venv/bin/activate
python test_workflow_imports.py
PROCESS_DATE_OVERRIDE=2026-03-24 python process_daily_sword_videos.py
```

`PROCESS_DATE_OVERRIDE` is useful for validating no-games behavior without changing the workflow schedule.

## Monitoring

```bash
gh run list --repo joewilsonai/SwordFinder --limit 10
gh run view <run-id> --repo joewilsonai/SwordFinder
```

Use logs/artifacts from the Actions run first. Local logs such as `daily_update.log` and `video_processing.log` are ignored and should not be committed.
