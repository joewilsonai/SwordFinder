# SwordFinder TODO

Last updated: 2026-05-08

## Current Baseline

- 2026 data pipeline is active.
- Railway API is the primary read path for the UI.
- Vercel static UI is deployed and serving core pages.
- GitHub Actions are active for daily data, video processing, and production smoke checks.
- Supabase and Azure credentials are not stored in git.

## Immediate Functional Priorities

- Add a proper search flow for hitters and pitchers.
- Add a clean `/date/:date` route for shareable daily sword slates; homepage now supports date selection with `?date=YYYY-MM-DD`.
- Expand hitter profile stats beyond the current top-row list.
- Expand pitcher profile stats for sword inducer rankings.
- Expand the operations/status page with recent GitHub workflow status.

## Cleanup/Hygiene Priorities

- Keep docs current with the Railway API-first architecture.
- Keep workflow triggers single-purpose to avoid duplicate video processing.
- Prefer `batter_name` for hitter-facing UI and API behavior.
- Keep temporary/debug scripts out of the root unless they are documented as operational tools.
- Add regression tests before changing API semantics.

## Later Ideas

- Social sharing cards for individual sword clips.
- Weekly and monthly highlight reels.
- Team and pitch-type filters.
- Admin retry controls for missing videos.
- Lightweight analytics charts for sword rates and score distributions.
