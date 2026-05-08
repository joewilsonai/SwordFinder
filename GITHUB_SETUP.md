# GitHub Operations

Repository:

- `https://github.com/PoliTwit1984/SwordFinder`

The repo is already initialized, connected to `origin`, and deployed from `main`.

## Required Secrets

Set these in GitHub repository settings under `Settings -> Secrets and variables -> Actions`:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABASE_URL
AZURE_STORAGE_CONNECTION_STRING
AZURE_CONTAINER_NAME
```

Do not commit `.env`, API keys, CSV exports, local videos, logs, or `.venv`.

## Workflows

- `Daily MLB Data Update`: scheduled daily and manually dispatchable.
- `Process Daily Sword Videos`: runs after the daily update succeeds and can be manually dispatched.
- `Production Smoke Check`: scheduled daily and manually dispatchable.

Manual workflow checks:

```bash
gh workflow list --repo PoliTwit1984/SwordFinder
gh run list --repo PoliTwit1984/SwordFinder --limit 10
```

Manual dispatch examples:

```bash
gh workflow run "Daily MLB Data Update" --repo PoliTwit1984/SwordFinder --ref main
gh workflow run "Process Daily Sword Videos" --repo PoliTwit1984/SwordFinder --ref main
gh workflow run "Production Smoke Check" --repo PoliTwit1984/SwordFinder --ref main
```

## Workflow File Pushes

If GitHub rejects a push that edits `.github/workflows/*.yml`, refresh the local GitHub CLI token with workflow scope:

```bash
gh auth refresh -h github.com -s workflow
```

Then push again:

```bash
git push origin main
```
