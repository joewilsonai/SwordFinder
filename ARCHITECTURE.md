# SwordFinder Architecture

SwordFinder has two main paths:

- **Read path:** the browser reads ranked sword data through the Railway API.
- **Write path:** GitHub Actions jobs fetch Statcast data, score candidates, resolve MLB clips, upload clips to Azure, and update Supabase.

## Production Topology

```mermaid
flowchart LR
    user[User browser]
    vercel[Vercel static UI<br/>ui-one-henna.vercel.app]
    api[Railway FastAPI<br/>swordfinder-production.up.railway.app]
    db[(Supabase<br/>mlb_pitches_enhanced)]
    azure[(Azure Blob Storage<br/>swordfinder-videos)]

    user --> vercel
    vercel -->|API-first reads| api
    api -->|read rows/counts/swords| db
    api -->|optional on-load clip hydration| statsapi
    api -->|optional on-load clip hydration| savant
    api -->|cache recovered clips| azure
    api -->|returns video_azure_blob_url| vercel
    user -->|plays MP4 clips| azure

    subgraph GitHub Actions
        daily[Daily MLB Data Update<br/>13:00 UTC]
        videos[Process Daily Sword Videos<br/>after daily update success or manual]
        smoke[Production Smoke Check<br/>15:30 UTC or manual]
    end

    statcast[pybaseball / Statcast]
    statsapi[MLB Stats API<br/>game feed live]
    savant[Baseball Savant<br/>sporty-videos]

    daily -->|fetch yesterday| statcast
    statcast -->|raw pitch rows| daily
    daily -->|score and upsert| db

    videos -->|query top uncached swords| db
    videos -->|resolve playId| statsapi
    videos -->|find MP4 URL| savant
    videos -->|upload clip| azure
    videos -->|write video_azure_blob_url| db

    smoke --> api
    smoke --> vercel
```

## Nightly Data Flow

```mermaid
sequenceDiagram
    participant GH as GitHub Actions
    participant DU as daily_update.py
    participant Statcast as pybaseball / Statcast
    participant DB as Supabase
    participant PV as process_daily_sword_videos.py
    participant MLB as MLB Stats API
    participant Savant as Baseball Savant
    participant Azure as Azure Blob

    GH->>DU: Run daily update for yesterday
    DU->>Statcast: Fetch pitch-level data
    Statcast-->>DU: Statcast rows
    DU->>DU: Calculate sword_score, perceived velocity, strike-zone miss distance
    DU->>DB: Upsert enriched pitch rows

    GH->>PV: Run video job after successful data update
    PV->>DB: Select top regular-season sword rows missing video_azure_blob_url
    PV->>MLB: Resolve game/inning/pitcher/batter to playId
    MLB-->>PV: playId
    PV->>Savant: Load sporty-videos page for playId
    Savant-->>PV: MP4 source URL
    PV->>Azure: Upload MP4 to swords/YYYY-MM-DD/
    Azure-->>PV: Public blob URL
    PV->>DB: Update video_azure_blob_url and video_processed_at
```

## Request Flow

```mermaid
sequenceDiagram
    participant Browser as Browser
    participant UI as Vercel UI
    participant API as Railway API
    participant DB as Supabase
    participant Azure as Azure Blob

    Browser->>UI: Load page assets
    UI->>API: GET /daily-slate, /profiles/.../swords, /data/rows, /data/count
    API->>DB: Read mlb_pitches_enhanced
    API->>API: Hydrate missing top-five/profile clips when requested
    DB-->>API: Rows with scores and video URLs
    API-->>UI: JSON
    UI-->>Browser: Render leaderboards, player pages, clip links
    Browser->>Azure: Stream MP4 when user opens a clip
```

## Important Boundaries

- **Supabase is the source of truth** for pitch rows, rankings, score fields, and cached video URLs.
- **Azure is only the clip cache.** Missing `video_azure_blob_url` does not mean MLB has no video; it means SwordFinder has not cached that clip yet or a resolver/upload step failed.
- **Railway is the API boundary** for production browser reads. Direct Supabase reads in the UI are fallback-only.
- **Vercel is static UI hosting.** It should not hold secrets or talk to Supabase with service-role credentials.
- **The Ops UI is read-only.** It reads Railway health, video backlog status, and season counts; it does not trigger video processing yet.
- **GitHub Actions owns scheduled writes.** The daily update writes data; the video workflow writes video URLs; the smoke workflow only verifies production.
- **The first video backlog is virtual.** A sword row with `sword_score > 0` and no `video_azure_blob_url` is treated as a pending video job. This avoids a new table while giving the app a real backlog surface.
- **On-load hydration is capped.** The homepage hydrates only the selected top five; profile pages hydrate visible missing profile clips up to `PROFILE_VIDEO_HYDRATION_MAX` so a profile view cannot drain a whole season by accident.

## Video Resolution Details

The video processor uses this chain:

1. Read top uncached sword candidates from Supabase.
2. Match each row to the MLB game feed by `game_pk`, `pitcher`, `batter`, `inning`, and `inning_topbot`.
3. Resolve the matching play event to a `playId`.
4. Load Baseball Savant `sporty-videos?playId=...`.
5. Extract the MP4 source.
6. Upload the MP4 to Azure Blob Storage.
7. Patch Supabase with `video_azure_blob_url`.

The play-id resolver normalizes half-inning labels because the database stores values such as `Top` and `Bot`, while MLB feed values are `top` and `bottom`.

## Video Backlog Controls

The backlog is exposed through read-only API endpoints:

- `GET /ops/video-backlog/status`
- `GET /ops/video-backlog/status?date=YYYY-MM-DD`
- `GET /ops/video-backlog?date=YYYY-MM-DD&limit=50`

The video worker still defaults to a conservative top-10 daily run, but it can now drain larger slices on demand:

```bash
python process_daily_sword_videos.py --date 2026-05-03 --top-n 25
python process_daily_sword_videos.py --date 2026-05-03 --all
```

The GitHub workflow keeps the default behavior. Manual/local runs can use `--date`, `--top-n`, `--all`, `VIDEO_TOP_N`, or `VIDEO_PROCESS_ALL=true`.

## Local Review / Backfill Path

```mermaid
flowchart LR
    operator[Operator laptop]
    local[Local scripts / review folders]
    api[Railway API]
    mlb[MLB Stats API + Baseball Savant]
    clips[Local sword_clips_to_review folders]
    azure[(Azure Blob)]
    db[(Supabase)]

    operator --> local
    local -->|query candidates| api
    api --> db
    local -->|resolve and download clips| mlb
    local --> clips
    local -->|when running production video processor| azure
    local -->|when running production video processor| db
```

The local review folders are for human inspection. Production state changes only happen when a script uploads to Azure and writes the resulting URL back to Supabase.
