# GitHub Actions Workflows

## Daily MLB Data Update

The `daily-update.yml` workflow automatically fetches yesterday's MLB data every day.

### Schedule
- Runs daily at 1:00 PM UTC (6 AM PST / 9 AM EST)
- Can also be triggered manually from the Actions tab

### What it does
1. Fetches yesterday's MLB pitch data from pybaseball
2. Calculates sword scores for each pitch
3. Calculates perceived velocity and strike zone distance
4. Updates percentiles using cached distributions
5. Inserts all data into Supabase
6. Logs the top sword swings of the day

### Required Secrets
Set these in your repository settings (Settings → Secrets and variables → Actions):

```
SUPABASE_URL                    # Your Supabase project URL
SUPABASE_ANON_KEY              # Supabase anonymous key
SUPABASE_SERVICE_ROLE_KEY      # Supabase service role key (if needed)
DATABASE_URL                   # PostgreSQL connection string
AZURE_STORAGE_CONNECTION_STRING # For video storage
AZURE_CONTAINER_NAME           # Azure container name
```

### Manual Trigger
1. Go to the Actions tab in your GitHub repository
2. Select "Daily MLB Data Update"
3. Click "Run workflow"
4. Choose the branch and click "Run workflow"

### Monitoring
- Check the Actions tab for run history
- Failed runs will show in red
- Logs are saved as artifacts for 7 days
- Download logs by clicking on a workflow run → Artifacts → daily-update-logs

### Troubleshooting
If the workflow fails:
1. Check the logs in the failed workflow run
2. Verify all secrets are set correctly
3. Ensure the database has enough space
4. Check if MLB API is available

### Cost Considerations
- GitHub Actions provides 2,000 free minutes/month for private repos
- Each run takes ~2-3 minutes
- 30 daily runs = ~90 minutes/month (well under the limit)

### Future Enhancements
- Add Slack/email notifications on failure
- Add data quality checks
- Process videos for top swords automatically
- Generate daily reports 