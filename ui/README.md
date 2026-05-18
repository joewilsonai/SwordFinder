# SwordFinder UI (2026)

Static frontend for SwordFinder using vanilla JavaScript + Tailwind CDN.

## Pages
- `/index.html` - date-selectable top-5 daily sword slate
- `/sword-info.html` - first-visit sword explainer, source clips, and lore
- `/leaderboards.html` - pitch-type, hitter, and pitcher leaderboards
- `/sword/[id].html` - shareable sword detail page
- `/ops.html` - API health, video cache status, and pending clip queue
- `/player/[id].html` - hitter sword profile
- `/pitcher/[id].html` - pitcher sword-inducer profile

## Local run
1. From `ui/` run:
```bash
python3 -m http.server 3000
```
2. Open:
- http://localhost:3000/index.html
- http://localhost:3000/leaderboards.html
- http://localhost:3000/leaderboards.html?view=hitters
- http://localhost:3000/leaderboards.html?range=season&pitch_type=FF
- http://localhost:3000/ops.html
- http://localhost:3000/sword/profile.html?id=805901
- http://localhost:3000/player/[id].html?id=571970
- http://localhost:3000/pitcher/[id].html?id=592332

## Config
Runtime config is in `assets/config.js`:
- `apiBaseUrl` (preferred, points to Railway API)
- `supabaseUrl` + `supabaseAnonKey` (optional fallback if no API URL is provided)
- `seasonYear`

To override in production, define `window.SWORDFINDER_CONFIG` before loading app modules.

## Vercel deployment
Deploy `ui/` as the project root.
- `vercel.json` includes rewrites for:
  - `/sword/:id` -> `/sword/profile?id=:id`
  - `/player/:id` -> `/player/profile?id=:id`
  - `/pitcher/:id` -> `/pitcher/profile?id=:id`

## Notes
- No build step required.
- Data is read via Railway API (`/daily-slate`, `/data/rows`, `/data/count`) by default.
- Videos stream directly from Azure blob URLs stored in Supabase.
- Leaderboard video cards use a `#t=0.25` media fragment so paused clips show a real preview frame instead of a black first frame.
