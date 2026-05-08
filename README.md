# SwordFinder

SwordFinder finds "sword" swings in MLB Statcast data: two-strike swinging strikes with slow bat speed, awkward swing characteristics, and enough context to rank, watch, and share the worst misses.

## Current Production Shape

- Static UI: `https://ui-one-henna.vercel.app`
- FastAPI backend: `https://swordfinder-production.up.railway.app`
- Database: Supabase table `mlb_pitches_enhanced`
- Video storage: Azure Blob container `swordfinder-videos`
- Automation: GitHub Actions on `main`

The browser reads through the Railway API by default:

- `GET /data/rows`
- `GET /data/count`
- `GET /swords/recent`

Direct browser reads from Supabase are only a fallback when `apiBaseUrl` is unset in `ui/assets/config.js`.

## Important Data Model Note

Raw Statcast rows use `player_name` as the pitcher name. SwordFinder UI and legacy sword endpoints should present swords from the hitter perspective:

- `batter` / `batter_name`: hitter who swung
- `pitcher` / `pitcher_name`: pitcher who induced the miss
- `player_name`: normalized to the hitter name in `/swords/*` responses
- `source_player_name`: original raw Statcast `player_name`

When adding UI or API functionality, prefer `batter_name` for hitters and `pitcher_name` for pitchers.

## Local Setup

```bash
cd /Users/joewilson/pythonprojects/swordfinder/SwordFinder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Secrets should come from local environment files, not source control. On this machine, project secrets may be sourced from `~/.luna/secrets/keys.env` or loaded from the local ignored `.env`.

## Run Locally

API:

```bash
source .venv/bin/activate
uvicorn api:app --reload --port 8000
```

UI:

```bash
cd ui
python3 -m http.server 3000
```

Open:

- `http://localhost:3000/index.html`
- `http://localhost:3000/leaderboards.html`
- `http://localhost:3000/player/[id].html?id=608369`
- `http://localhost:3000/pitcher/[id].html?id=660787`

## Daily Operations

GitHub Actions:

- `Daily MLB Data Update`: fetches yesterday's Statcast data, calculates sword scores, and updates Supabase.
- `Process Daily Sword Videos`: runs after the daily data workflow succeeds, then attempts videos for the top sword swings.
- `Production Smoke Check`: checks Railway API health, live data, recent swords, and core Vercel routes.

Useful local checks:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_api_sword_serialization.py tests/test_ui_config.py -q
python test_workflow_imports.py
curl -fsS https://swordfinder-production.up.railway.app/health
curl -fsS "https://swordfinder-production.up.railway.app/data/count?select=id&game_date=gte.2026-01-01&sword_score=gt.0"
```

## Key Files

- `api.py`: FastAPI backend and API-first UI data endpoints.
- `daily_update.py`: daily Statcast ingestion and scoring.
- `process_daily_sword_videos.py`: video processing workflow target.
- `ui/`: static Vercel frontend.
- `.github/workflows/`: scheduled/manual automation.
- `PROGRESS_2026.md`, `DECISIONS_2026.md`, `FINAL_REPORT_2026.md`: revival notes and operating decisions.

## Next Functional Work

Now that the production path is stable, the next useful functionality should build on the existing API-first UI:

- Better search and player lookup.
- Dedicated date pages for daily sword slates.
- More complete hitter/pitcher profile stats.
- Video backlog/retry tooling surfaced in a small admin/status view.
