# SwordFinder Maintainability Audit

Date: 2026-05-17

## Current Read

SwordFinder is a real production app with a working Railway API, Vercel UI,
Supabase data store, Azure video cache, GitHub Actions cron, and X posting path.
The project is not throwaway code, but it has accumulated revival-era script
sprawl. The first oversized API seam has been cut down, and the next cleanup
target is the extracted X-sharing service.

## Fixed In This Pass

- Protected server-side X posting and xAI draft usage with an admin token gate.
  Public draft requests now fall back to a deterministic template instead of
  spending xAI calls.
- Preserved browser-session text posting while preventing unauthenticated use
  of configured server OAuth2 tokens.
- Disabled the native top-sword posting button for browser-only sessions; the
  protected server posting endpoint now requires operator access.
- Added tests for X admin gating, browser-session preference, and public draft
  fallback.
- Fixed daily percentile updates when the optional Supabase
  `execute_sql_query` RPC is missing by falling back to paginated table reads.
- Fixed the pitch-type percentile SQL execution bug and added regression tests.
- Changed percentile cache naming to season-scoped files and ignored those cache
  artifacts in git.
- Hardened production smoke workflow diagnostics with labeled curls, retries,
  timeouts, and clearer failure points.
- Corrected stale docs/config references: old GitHub owner, old framework
  wording, and the stale Replit app target.
- Replaced remaining live-path broad exception catches outside `legacy/`.
- Extracted X sharing routes and service helpers out of `api.py` into
  `api_routes/share_x.py` and `api_services/x_sharing.py`.
- Moved sword-row normalization into `api_services/sword_rows.py`.
- Added mobile-first guardrails to the static UI: viewport-fit metadata,
  48px touch targets for primary controls, 16px input text, and no horizontal
  overflow at common phone/tablet/desktop widths.
- Added local 4173/127.0.0.1 origins to default CORS so static UI QA can run
  against a local API without custom env overrides.

## Spaghetti Hotspots

- `api.py` is down to roughly 800 lines, but it still owns mixed route groups:
  data reads, profile APIs, video hydration, ops routes, and legacy public
  endpoints.
- `api_services/x_sharing.py` is the new hotspot at roughly 1,100 lines. It
  should be split into OAuth session handling, X API client calls, draft
  formatting, and route request models.
- `update_percentiles_daily.py` is now reliable but should become a small
  command wrapper around a `services/percentiles.py` module.
- `ui/assets/index.js` is a 575-line controller with state, templates, fetches,
  share flows, rendering, and event binding in one file.
- The repo root contains many historical one-off scripts. Most are ignored or
  harmless, but the live maintenance surface is hard to see at a glance.
- Large local data/video/log artifacts are present in the working directory but
  are not tracked by git. `.gitignore` covers them; keep it that way.

## Recommended Refactor Sequence

1. Finish splitting `api.py` into focused route modules:
   - `api/routes/data.py`
   - `api/routes/profiles.py`
   - `api/routes/ops.py`
   - `api/services/video_hydration.py`
2. Split `api_services/x_sharing.py` into:
   - `api_services/x_oauth.py`
   - `api_services/x_client.py`
   - `api_services/x_drafts.py`
   - `api_models/share_x.py`
3. Move ETL and maintenance scripts into `scripts/ingest/`, `scripts/video/`,
   and `scripts/maintenance/`, leaving thin root wrappers only where GitHub
   Actions depends on them.
4. Extract percentile distribution logic into `api/services/percentiles.py` or
   `scripts/lib/percentiles.py`, then keep `update_percentiles_daily.py` as the
   CLI entry point.
5. Split `ui/assets/index.js` into state, API client, renderers, and share-X
   modules.
6. Add one small shared auth helper for operator-gated endpoints so future ops
   routes do not grow their own auth checks.
7. Add protected endpoint smoke coverage once `SWORDFINDER_ADMIN_TOKEN` is
   configured as a GitHub Actions secret.

## Security Notes

- Server-side posting endpoints now require `SWORDFINDER_ADMIN_TOKEN` or
  `X_POST_ADMIN_TOKEN`.
- Accepted request forms are `Authorization: Bearer <token>` and
  `X-SwordFinder-Admin-Token: <token>`.
- Without admin access, `/share/x/oauth/status` hides server token connection
  details and `/share/x/draft` returns a non-AI template.
- `/share/x/post` can still post through a user browser OAuth session; server
  OAuth2 token posting requires admin access.

## Verification

- `source ~/.luna/secrets/keys.env && .venv/bin/pytest tests/test_share_x_draft.py tests/test_percentile_update.py -q`
- `source ~/.luna/secrets/keys.env && .venv/bin/pytest -q`
- `source ~/.luna/secrets/keys.env && .venv/bin/python -m compileall api.py api_routes api_services update_percentiles_daily.py daily_update.py process_daily_sword_videos.py`
- `source ~/.luna/secrets/keys.env && .venv/bin/python test_workflow_imports.py`
- Live checks: Railway `/health`, latest row lookup, video backlog status, and `https://swordfinder.com`.
- Extracted and ran the production smoke workflow shell locally against Railway and Vercel.
- Playwright mobile audit with mocked full UI data at 375x667, 390x844,
  768x1024, and 1280x720.
