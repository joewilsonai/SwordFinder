# GitHub Actions Workflows

## Daily MLB Data Update

File: `daily-update.yml`

- Runs daily at 13:00 UTC.
- Can be triggered manually.
- Fetches yesterday's Statcast data, scores swords, and updates Supabase.

## Process Daily Sword Videos

File: `process-daily-videos.yml`

- Runs after `Daily MLB Data Update` completes successfully.
- Can be triggered manually.
- Processes the top sword swings for the target date and uploads available videos to Azure Blob.

The video workflow is intentionally not independently scheduled. The `workflow_run` trigger keeps it tied to a successful data refresh and avoids duplicate daily video passes.

## Production Smoke Check

File: `production-smoke.yml`

- Runs daily at 15:30 UTC.
- Can be triggered manually.
- Checks Railway `/health`, live API data, `/swords/recent`, video backlog status, and core `swordfinder.com` routes.

## Required Secrets

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABASE_URL
AZURE_STORAGE_CONNECTION_STRING
AZURE_CONTAINER_NAME
```

## Useful Commands

```bash
gh workflow list --repo joewilsonai/SwordFinder
gh run list --repo joewilsonai/SwordFinder --limit 10
gh run view <run-id> --repo joewilsonai/SwordFinder
```
