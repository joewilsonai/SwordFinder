# Decisions Log - 2026 Revival

## 1) Year-scoped backfill and percentile strategy
- Decision: Keep 2025 historical data untouched and run 2026-only ingestion/scoring/percentiles.
- Why: Spec requires additive updates and no regression to 2025 season data.
- Impact: 2026 data is independently refreshable without rewriting prior-season values.

## 2) Replace offset pagination with ID-based pagination for large Supabase scans
- Decision: Use keyset pagination (`id > last_id`) in backfill/scoring/percentile scripts.
- Why: Offset pagination hit practical API limits and led to incomplete reads for 2026 rows.
- Impact: Full 2026 dataset (`83,806` rows) can be read and processed reliably.

## 3) Percentile fallback when SQL RPC times out
- Decision: Introduce `calculate_percentiles_year.py` (Python/Pandas + batched upsert) as fallback.
- Why: `calculate_percentiles_sql.py` failed with statement timeout using RPC `execute_sql`.
- Impact: 2026 percentile fields were fully populated without modifying 2025 values.

## 4) Additive schema alignment instead of deleting/changing existing behavior
- Decision: Add missing columns if expected by scripts:
  - `bat_speed_percentile_overall`
  - `movement_total`
- Why: Daily and yearly percentile scripts referenced these fields; column mismatch caused runtime failures.
- Impact: Pipeline now matches script contracts and automation can update percentiles cleanly.

## 5) Workflow hardening while preserving schedule behavior
- Decision: Re-enable workflows and apply non-breaking updates:
  - setup-python v5
  - workflow concurrency groups
  - gate video workflow when dependency workflow fails
  - keep existing schedule windows
- Why: Restore reliability for 2026 season without changing operational cadence.
- Impact: Manual dispatch passed, workflows active again.

## 6) Frontend architecture for fast revival
- Decision: Ship static UI in `ui/` with vanilla JS + Tailwind CDN and direct Supabase REST reads.
- Why: No build step requirement; fastest path to deployable, maintainable pages.
- Impact: Required pages delivered and deployed on Vercel with route rewrites.

## 7) Dynamic profile route handling on Vercel
- Decision: Keep requested files (`player/[id].html`, `pitcher/[id].html`) and use stable `profile.html` rewrite targets for runtime routing.
- Why: Bracket-named files caused rewrite reliability issues under Vercel routing.
- Impact: `/player/:id` and `/pitcher/:id` now resolve successfully in production.

## 8) API-first frontend reads for 2026 production
- Decision: Move UI reads to Railway API (`/data/rows`, `/data/count`) as primary path; keep direct Supabase mode only as optional fallback.
- Why: Browser-side anon reads are sensitive to RLS/policy drift and had inconsistent visibility in production.
- Impact: Stable 2026 data rendering from server-managed credentials; public UI no longer requires embedded Supabase keys.

## 9) Server-side Supabase credential preference
- Decision: Prefer `SUPABASE_SERVICE_ROLE_KEY` for backend reads, fallback to anon only if service role key is absent.
- Why: Backend needs consistent, policy-independent read access for public endpoints and UI aggregation.
- Impact: `/health`, `/swords/*`, and `/data/*` endpoints return live 2026 data reliably.
