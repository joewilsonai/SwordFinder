# Progress Log - 2026 Revival

## 2026-04-12 12:58 CDT

### Completed
- Loaded and executed `CODEX2_SPEC.md` workflow.
- Finished Phase 1 audit and wrote `AUDIT_2026.md`.
- Validated both external systems:
  - Supabase credentials working
  - Azure Blob credentials working
- Verified data status:
  - Latest date is `2025-08-23`
  - No 2026 rows yet
- Audited workflows:
  - Both GitHub Actions were `disabled_inactivity`
- Collected full inventory of hardcoded `2025` references.

### Next Steps
- Phase 2: modernize active scripts to dynamic season/year behavior.
- Create `download_full_2026_season.py` with correct 2026 opening day date.
- Add dry-run paths where missing and run validation tests.

### Blockers
- None.

---

## 2026-04-12 13:14 CDT

### Completed
- Phase 2 complete:
  - Modernized active scripts for dynamic year/date usage.
  - Added `download_full_2026_season.py`.
  - Added dry-run support across key ingestion/video scripts.
  - Added `env_config.py` defensive env parsing for malformed `.env` lines.
- Phase 3 complete:
  - Backfilled 2026 data through yesterday (`2026-04-11`).
  - Built and ran `backfill_2026_season.py` with duplicate-safe key matching.
  - Fixed sword-score batch logic and ran `calculate_all_sword_scores.py --year 2026`.
  - SQL percentile RPC timed out; implemented robust year-scoped fallback `calculate_percentiles_year.py` and upserted all 2026 rows.
  - Verified Supabase 2026 range and counts:
    - `COUNT(*) = 83,806`
    - `MIN(game_date) = 2026-03-25`
    - `MAX(game_date) = 2026-04-11`
- Phase 4 complete:
  - Re-enabled both GitHub workflows via API.
  - Manual dispatch test succeeded for `Daily MLB Data Update` (run `24312929566`).
  - Manual dispatch test succeeded for `Process Daily Sword Videos` (run `24313189234`).
  - Updated workflow files locally:
    - `actions/setup-python@v5`
    - concurrency groups
    - `PYTHONUNBUFFERED=1`
    - workflow-run success gate for video workflow
  - Workflow file push is pending `workflow` OAuth scope (current token cannot update `.github/workflows/*`).
  - Added `PROCESS_DATE_OVERRIDE` to `process_daily_sword_videos.py` and verified no-games date exits cleanly.
- Phase 5 complete (initial frontend ship):
  - Built static vanilla JS + Tailwind pages:
    - `ui/index.html`
    - `ui/leaderboards.html`
    - `ui/player/[id].html`
    - `ui/pitcher/[id].html`
  - Added shared assets/data layer and profile route handling.
  - Added Vercel config with route rewrites for `/player/:id` and `/pitcher/:id`.
  - Deployed production UI: `https://ui-one-henna.vercel.app`

### Blockers
- `execute_sql` percentile path in Supabase times out for 2026-scale updates.
  - Mitigated with year-scoped Python percentile fallback script.

### Next Steps
- Write `DECISIONS_2026.md` and `FINAL_REPORT_2026.md`.
- Optional: attach custom domain in Vercel dashboard (not configured in repo/CLI yet).
- Optional hardening: remove/rotate leaked public anon key from `TODO.md` and migrate UI config to env-injected runtime.

---

## 2026-04-12 16:47 CDT

### Completed
- Deployed backend to Railway project `swordfinder` and attached production domain:
  - `https://swordfinder-production.up.railway.app`
- Added explicit process start for Railway via `Procfile` (`gunicorn` + `uvicorn` worker).
- Fixed backend health check logic to report DB connectivity correctly.
- Switched backend Supabase auth to prefer `SUPABASE_SERVICE_ROLE_KEY` (fallback to anon only if missing).
- Added API-first data endpoints for static UI:
  - `GET /data/rows`
  - `GET /data/count`
  - Supports safe read-only filtering for `mlb_pitches_enhanced`.
- Set Railway env vars required for production reads:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `CORS_ORIGINS`
- Verified live 2026 API data:
  - `/data/count?...game_date=2026...&sword_score=gt.0` returned `8236`
- Updated UI to use Railway API by default (no direct Supabase key required in browser):
  - `ui/assets/config.js` now uses `apiBaseUrl`
  - `ui/assets/supabase-rest.js` routes `fetchRows`/`fetchCount` through API when `apiBaseUrl` is set
- Redeployed UI to Vercel production alias:
  - `https://ui-one-henna.vercel.app`
- Verified CORS allows UI origin on Railway API.

### Notes
- Legacy API routes (`/swords/*`) were failing due strict response typing on nullable fields; model was relaxed and endpoint now returns data successfully.
