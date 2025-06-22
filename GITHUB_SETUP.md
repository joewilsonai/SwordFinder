# GitHub Setup Guide for SwordFinder

## 1. Initialize Git Repository

First, make sure you're in the SwordFinder directory and initialize git:

```bash
cd /Users/joewilson/pythonprojects/swordfinder/SwordFinder
git init
git add .gitignore
git commit -m "Initial commit with .gitignore"
```

## 2. Create GitHub Repository

1. Go to [GitHub.com](https://github.com)
2. Click the "+" icon in the top right → "New repository"
3. Name it: `swordfinder`
4. Description: "MLB sword swing finder using 2025 bat tracking data"
5. Keep it **Private** initially (since it contains your data)
6. DON'T initialize with README (we already have one)
7. Click "Create repository"

## 3. Add Remote and Push

After creating the repo, GitHub will show you commands. Use these:

```bash
# Add remote origin (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/swordfinder.git

# Add all files EXCEPT those in .gitignore
git add .
git commit -m "Initial commit: SwordFinder v2 with bat tracking analysis"

# Push to GitHub
git branch -M main
git push -u origin main
```

## 4. Verify .env is NOT uploaded

**CRITICAL**: Make sure your `.env` file with credentials is NOT in the repo:

```bash
# This should show nothing (meaning .env is ignored)
git ls-files | grep -E "\.env|mlb_2025.*\.csv"
```

## 5. Add GitHub Secrets for Actions

Go to your repo on GitHub:
1. Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add these secrets:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=postgresql://...
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_CONTAINER_NAME=swordfinder-videos
```

## 6. Create GitHub Action for Daily Updates

We'll create the workflow file next. This will run daily_update.py automatically.

## Important Notes

- The CSV files (227MB+) won't be uploaded due to .gitignore
- Your .env file with secrets won't be uploaded
- The perceived_velocity.log won't be uploaded
- Videos won't be uploaded

## Recommended First Commits

After initial commit, consider these logical commits:

```bash
# Commit 1: Core documentation
git add README.md TODO.md QUICK_START_UI.md
git commit -m "docs: Add comprehensive documentation"

# Commit 2: Database scripts
git add *.sql
git commit -m "feat: Add database schema and SQL scripts"

# Commit 3: Data processing scripts
git add download_full_2025_season.py upload_data_correctly.py calculate_*.py
git commit -m "feat: Add data processing and calculation scripts"

# Commit 4: Video processing
git add *video*.py clean_video_processor.py
git commit -m "feat: Add video processing pipeline"

# Commit 5: API and daily updates
git add api.py daily_update.py update_percentiles_daily.py
git commit -m "feat: Add API and automated daily updates"

# Commit 6: Legacy reference
git add legacy/
git commit -m "docs: Add legacy v1 code for reference"
```

Or just do one big commit if you prefer! 