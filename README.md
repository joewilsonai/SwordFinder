<div align="center">

# SwordFinder

**A live MLB data product for finding, scoring, watching, and sharing the ugliest strikeout swings in baseball.**

SwordFinder ranks "swords": two-strike swinging-strike moments where the hitter is so fooled that the bat dies out front. The site combines Statcast pitch data, bat tracking, its own Sword Score, MLB video clips and shareable leaderboards.

[![Live](https://img.shields.io/badge/Live-swordfinder.com-22c55e)](https://swordfinder.com)
[![MIT](https://img.shields.io/badge/License-MIT-d97757)](LICENSE)

[Try it](https://swordfinder.com) · [How it works](https://swordfinder.com/ops) · [What's a sword?](https://swordfinder.com/sword-info)

<br />

<img src="docs/assets/swordfinder-leaderboards.png" alt="SwordFinder pitch-type leaderboard with MLB sword clips" width="900" />

</div>

---

## Why it exists

Baseball fans already know a sword when they see one: the swing is late, awkward, and over before the bat finishes. SwordFinder turns that baseball-internet moment into a ranked product:

- Which hitter got fooled the worst today?
- Which pitch type produces the nastiest swords?
- Which pitchers are inducing the most ugly strikeout swings?
- Which hitters are getting slain most often?

The important product rule is **No K, no sword**. A hitter can look terrible on pitch two and still win the at-bat on pitch three. SwordFinder focuses on the finished strikeout moment, because that is the clip people remember.

## Features

- **Daily sword slate** with date picker, top-five rankings, score metrics, and video-ready counts.
- **Pitch-type explorer** for season leaderboards by family or individual pitch type, such as fastballs, sliders, sinkers, cutters, and changeups.
- **Leaderboard views** for pitch types, hitter sword leaders, and pitcher sword leaders.
- **Shareable sword detail pages** at `/sword/{id}` with video, score breakdown, copy link, native share, and X intent.
- **Hitter and pitcher profiles** with each player's season of swords.
- **Sword Info page** with the term explainer, embedded source videos, and replayable first-visit onboarding.

## The Sword Score

A sword is a swing and miss on strike three, with bat tracking and a bat speed under 60 mph. The score starts at 50 and adds up to 50 for a slow bat, up to 25 for swing tilt, and up to 25 for swing length. 90 makes the board and 100 is elite. See `sword_score` in [`pipeline/update.py`](pipeline/update.py).

## How it works

1. **A GitHub Action runs every morning** (`.github/workflows/daily.yml`) and calls `pipeline/update.py`.
2. **It reads the previous days' pitches from Baseball Savant**, keeps the swords, and scores them.
3. **It finds each sword's clip**: the copy already in Azure Blob Storage if there is one, otherwise MLB's, which it copies in.
4. **It commits plain JSON to `ui/data/`.** Vercel deploys that as a static site.
5. **The browser reads the JSON directly** and filters it with `ui/assets/query.js`.

There is no database and no API server. That's on purpose: the first version ran on Supabase, Railway, Azure, Vercel and GitHub Actions, and when the database paused and the API disappeared, the site went dark. Nothing here can pause.

The daily run commits a check-in even when there are no games, which keeps GitHub from turning the schedule off. `/ops` explains the scoring and shows the last check-in.

## Stack

- **Frontend:** static HTML, vanilla JavaScript modules, Tailwind built once to `ui/assets/tailwind.css` (see `tailwind.config.cjs`), custom CSS, on Vercel from `ui/`
- **Data:** `pipeline/update.py`, Python standard library plus `azure-storage-blob` for copying clips
- **Clips:** Azure Blob Storage
- **Automation:** one GitHub Actions workflow

## Key routes

| Route | Purpose |
| --- | --- |
| [`/`](https://swordfinder.com) | Daily top-five sword slate |
| [`/leaderboards`](https://swordfinder.com/leaderboards) | Pitch-type, hitter, and pitcher leaderboards |
| [`/sword-info`](https://swordfinder.com/sword-info) | Explainer and source clips |
| [`/ops`](https://swordfinder.com/ops) | How it works, last check-in and data counts |
| `/sword/{id}` | Shareable sword detail page |
| `/player/{id}` | Hitter sword profile |
| `/pitcher/{id}` | Pitcher sword-inducer profile |

## Run locally

```bash
python3 pipeline/update.py --days 3 --clips 0   # refresh the data; no Azure key needed with --clips 0
cd ui && python3 -m http.server 3000
```

Then open <http://localhost:3000>. The clean URLs (`/leaderboards`, `/sword/{id}`) are Vercel rewrites from `ui/vercel.json`, so locally use the file names: `/leaderboards.html`, `/ops.html`, `/sword/profile.html?id=...`.

## Tests

```bash
python3 -m unittest discover -s tests
node --test tests/query.test.mjs
```

## What broke

The first version ran on five services. In 2026 the Railway API disappeared, GitHub switched off the daily jobs for inactivity, and Supabase paused a 2 GB database too big to restore on the free plan. A health check failed for days along the way and nobody was reading it.

The rewrite keeps the part that matters. Instead of every pitch in a database, it keeps only the 2,399 swords of 2026, about 300 KB once compressed. If the daily job stops, `/ops` shows it. Only the current season is rebuilt so far, and about 120 swords have no clip because MLB no longer serves them.

## License

[MIT](LICENSE) for the project code. MLB and Statcast data and MLB video rights belong to their owners. Not affiliated with MLB.
