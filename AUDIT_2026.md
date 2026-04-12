# SwordFinder 2026 Audit

Date: 2026-04-12  
Executor: Codex (autonomous Phase 1)

## Scope Completed

1. Read core markdown docs and legacy references:
   - `README.md`
   - `TODO.md`
   - `CODEX2_SPEC.md`
   - `GITHUB_SETUP.md`
   - `QUICK_START_UI.md`
   - `setup_daily_update.md`
   - `percentile_calculation_plan.md`
   - `extension_and_perceived_velocity_summary.md`
   - `ui/README.md`
   - `legacy/README_v1.md`
   - `viderror.md`
2. Validated Supabase and Azure credentials from local `.env`.
3. Audited current database freshness and year coverage.
4. Audited hardcoded `2025` references in codebase.
5. Audited GitHub Actions workflow status and recent run history.

## Credential Checks

## Supabase
- Status: `PASS`
- Auth method tested: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` against PostgREST
- Result: API responded successfully; table `mlb_pitches_enhanced` is queryable.

## Azure Blob
- Status: `PASS`
- Auth method tested: `AZURE_STORAGE_CONNECTION_STRING` via `azure-storage-blob`
- Result:
  - Account access successful
  - Containers listed: `swordfinder-videos`, `videos`
  - Configured container `swordfinder-videos` exists and is readable

## Database Freshness

Table: `mlb_pitches_enhanced`

- Total rows: `589,291`
- 2025 rows: `589,291`
- 2026 rows: `0`
- Rows with `video_azure_blob_url`: `883`
- Earliest `game_date`: `2025-03-20`
- Latest `game_date`: `2025-08-23`

Notes:
- The spec expectation ("late June 2025") is outdated. Data currently extends through **August 23, 2025**.
- No 2026 season data is present yet.

## Hardcoded `2025` References Audit

### Active scripts requiring 2026 modernization

- `download_full_2025_season.py`
- `process_regular_season_videos.py`
- `process_regular_season_videos_smart.py`
- `process_top_videos_only.py`
- `process_all_sword_videos.py`
- `get_top_n_videos.py`
- `upload_data_correctly.py`
- `get_play_ids_on_demand.py` (example text references)

### Test/legacy/docs also containing `2025`

- `test_june20_swords_csv.py`
- `legacy/app.py`
- `legacy/templates/*.html`
- SQL/docs comments with historical 2025 language

### High-risk finding

- `TODO.md` contained a literal Supabase anon key string at end-of-file.
- Status: **remediated during revival** (key string removed from `TODO.md`, UI config moved to `ui/assets/config.js`).

## GitHub Actions Audit

Repository: `PoliTwit1984/SwordFinder`

Workflows discovered:
- `Daily MLB Data Update` (`.github/workflows/daily-update.yml`)
- `Process Daily Sword Videos` (`.github/workflows/process-daily-videos.yml`)

Current workflow state (GitHub API):
- `disabled_inactivity` for both workflows

Recent run history:
- Last successful scheduled runs were on `2025-08-24`
- Daily runs were healthy at that time (success), then automation went dormant

Implications:
- Automation is not currently active for 2026 and must be explicitly re-enabled.

## Phase 1 Exit Criteria

- [x] Docs reviewed
- [x] Supabase credentials validated
- [x] Azure credentials validated
- [x] Latest DB date verified
- [x] Hardcoded 2025 references identified
- [x] Workflow status audited

Phase 1 complete. Proceeding to Phase 2.
