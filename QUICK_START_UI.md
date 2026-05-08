# SwordFinder UI Quick Start

The current UI is a static vanilla JavaScript app in `ui/`. There is no build step.

## Local Run

```bash
cd /Users/joewilson/pythonprojects/swordfinder/SwordFinder/ui
python3 -m http.server 3000
```

Open:

- `http://localhost:3000/index.html`
- `http://localhost:3000/leaderboards.html`
- `http://localhost:3000/player/[id].html?id=608369`
- `http://localhost:3000/pitcher/[id].html?id=660787`

## Runtime Config

The UI reads `ui/assets/config.js`.

Production uses:

```js
window.SWORDFINDER_CONFIG = {
  apiBaseUrl: "https://swordfinder-production.up.railway.app",
  supabaseUrl: "",
  supabaseAnonKey: "",
  seasonYear: 2026,
  appName: "SwordFinder",
};
```

When `apiBaseUrl` is set, the browser uses Railway endpoints and does not need Supabase credentials.

## Deploy

Deploy `ui/` as the Vercel project root. The existing `ui/vercel.json` rewrites dynamic profile routes:

- `/player/:id`
- `/pitcher/:id`

Production URL:

- `https://ui-one-henna.vercel.app`

## Data Access

Use helpers in `ui/assets/supabase-rest.js`:

- `fetchRows(table, params)`
- `fetchCount(table, params)`
- `latestSeasonRange()`
- `linkForPlayer(row)`
- `linkForPitcher(row)`

Prefer these helpers instead of hand-rolling fetch calls so the UI stays API-first.

## Local Verification

```bash
cd /Users/joewilson/pythonprojects/swordfinder/SwordFinder
PYTHONPATH=. .venv/bin/pytest tests/test_ui_config.py -q
for route in / /leaderboards /player/608369 /pitcher/660787 /assets/index.js; do
  curl -fsS -o /dev/null "https://ui-one-henna.vercel.app$route"
done
```
