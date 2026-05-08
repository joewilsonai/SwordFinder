# Final Report - SwordFinder 2026 Revival

## Outcome
SwordFinder has been revived for the 2026 MLB season and is operational end-to-end again.

## What is working

### Data pipeline
- 2026 season backfill completed through yesterday (`2026-04-11`).
- Supabase verification:
  - 2026 rows: `83,806`
  - Min date: `2026-03-25`
  - Max date: `2026-04-11`
- 2026 sword scores calculated (`calculate_all_sword_scores.py --year 2026`).
- 2026 percentiles populated with year-scoped fallback pipeline (`calculate_percentiles_year.py`).

### Automation
- GitHub Actions workflows re-enabled from `disabled_inactivity` to `active`:
  - `Daily MLB Data Update`
  - `Process Daily Sword Videos`
- Manual dispatch test succeeded:
  - Workflow: `Daily MLB Data Update`
  - Run ID: `24312929566`
  - Result: success
- Manual dispatch test succeeded:
  - Workflow: `Process Daily Sword Videos`
  - Run ID: `24313189234`
  - Result: success
- Video pipeline no-games behavior validated (script exits cleanly with no data).

### Frontend
- Implemented required pages in vanilla JS + Tailwind CDN:
  - `ui/index.html`
  - `ui/leaderboards.html`
  - `ui/player/[id].html`
  - `ui/pitcher/[id].html`
- Added reusable data/helpers + styling system in `ui/assets/`.
- Deployed to Vercel production:
  - `https://ui-one-henna.vercel.app`
- Route rewrites validated:
  - `/leaderboards`
  - `/player/:id`
  - `/pitcher/:id`

## What is not fully ideal yet
- SQL RPC percentile updater (`calculate_percentiles_sql.py`) still times out on larger updates.
  - Mitigation exists (`calculate_percentiles_year.py`), but SQL path itself remains constrained.
- Workflow YAML hardening was later committed and pushed.
  - Video processing now runs after successful data updates instead of also running on a separate schedule.
  - Production smoke checks cover the live API and UI.
- Vercel custom domain was not attached from CLI in this run.
  - Production alias is active on `ui-one-henna.vercel.app`.
- UI runtime config is API-first.
  - `ui/assets/config.js` points at Railway and leaves browser Supabase keys blank by default.

## Key risks found and mitigated
- Offset pagination caused incomplete reads/processing.
  - Fixed by moving to ID-based pagination in new/updated scripts.
- Score backfill loop could skip rows.
  - Fixed with deterministic pagination and batch upsert approach.
- Live DB schema drift vs script expectations.
  - Added missing columns additively (`bat_speed_percentile_overall`, `movement_total`).

## What I would do differently next pass
1. Add a single schema migration baseline (`migrations/2026_revival.sql`) and run it before any script execution.
2. Introduce one canonical pagination utility to eliminate future offset regressions.
3. Keep direct Supabase reads as fallback only; use Railway API reads in production.
4. Keep lightweight smoke checks for API, frontend routes, and script imports.

## Files produced for this revival
- `AUDIT_2026.md`
- `PROGRESS_2026.md`
- `DECISIONS_2026.md`
- `FINAL_REPORT_2026.md`
- New/updated pipeline and UI files described in git diff.
