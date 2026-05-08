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
    UI->>API: GET /data/rows, /data/count, /swords/recent
    API->>DB: Read mlb_pitches_enhanced
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
- **GitHub Actions owns scheduled writes.** The daily update writes data; the video workflow writes video URLs; the smoke workflow only verifies production.

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
