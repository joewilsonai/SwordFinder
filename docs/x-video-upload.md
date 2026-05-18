# X Video Upload Runbook

Last verified: 2026-05-17.

This document is about posting videos to X/Twitter. It is not about the xAI Grok API.

## The Correct SwordFinder Path

Use the X API, not xAI, for posting video.

SwordFinder's working production path is:

1. Download the cached Azure MP4 for the selected sword.
2. Upload the video with OAuth 1.0a user context to:
   `https://upload.twitter.com/1.1/media/upload.json`
3. Use the chunked video flow:
   `INIT -> APPEND -> FINALIZE -> optional STATUS polling`
4. Read the returned `media_id_string`.
5. Create the post through X API v2:
   `POST https://api.x.com/2/tweets`
6. Attach the uploaded video with:
   `{"media": {"media_ids": ["<media_id_string>"]}}`

Current SwordFinder code path:

- `api.py::upload_and_post_top_sword_video`
- `api.py::upload_x_video_bytes`
- `api.py::create_x_post`
- `POST /share/x/top-sword`

## What xAI Is For

xAI/Grok is only used for optional text draft generation in SwordFinder:

- `POST /share/x/draft`
- `XAI_API_KEY`
- `https://api.x.ai/v1/chat/completions`

xAI does not publish an X post and does not attach media to a post. Do not use the xAI Files API for SwordFinder X posting.

## Credentials Required

For native video posting, keep these in `~/.luna/secrets/keys.env` and Railway variables. Never commit values.

Operator gate for server-side posting and xAI drafts:

- `SWORDFINDER_ADMIN_TOKEN` (or `X_POST_ADMIN_TOKEN`)

Send it as `Authorization: Bearer <token>` or `X-SwordFinder-Admin-Token: <token>`.
Without the admin token, public draft requests use a template draft, server-token
status is hidden, and server-side X posting returns `403`.

OAuth 1.0a video upload and media-backed post:

- `X_API_KEY` / `TWITTER_API_KEY`
- `X_API_SECRET` / `TWITTER_API_SECRET`
- `X_ACCESS_TOKEN_B64`
- `X_ACCESS_TOKEN_SECRET_B64`
- `X_SCREEN_NAME`
- `X_USER_ID`
- `X_MEDIA_UPLOAD_ENABLED=true`

OAuth 2.0 can remain configured for non-media posting and token refresh:

- `X_CLIENT_ID_B64`
- `X_CLIENT_SECRET_B64`
- `X_OAUTH2_ACCESS_TOKEN_B64`
- `X_OAUTH2_REFRESH_TOKEN_B64`
- `X_OAUTH2_SCOPE`

Use `_B64` for token-like values in Railway. It avoids CLI/env parsing problems with special characters. If setting `X_OAUTH2_SCOPE` through the Railway CLI, use comma-separated scopes because spaces can be truncated by shell/CLI parsing. The app parser accepts both commas and whitespace.

## Why Not OAuth2 Media Upload?

X currently documents a v2 media upload flow using:

- `POST /2/media/upload/initialize`
- `POST /2/media/upload/{id}/append`
- `POST /2/media/upload/{id}/finalize`
- `GET /2/media/upload`

SwordFinder keeps an OAuth2 implementation as a fallback only when a token actually has `media.write`. In our verified production setup, OAuth2 refresh works and `offline.access` is granted, but `media.write` is not granted and `/2/media/upload/initialize` returns `403 Forbidden`.

The OAuth1 v1.1 media endpoint was verified to work with the same X app/user context:

- OAuth1 media `INIT`: `202`
- Full upload/finalize of the May 6 Corey Seager MP4: succeeded
- Public native video post: succeeded

Therefore, for SwordFinder, OAuth1 is the primary video upload path.

## Operational Commands

Dry-run the selected day's top sword without posting:

```bash
source ~/.luna/secrets/keys.env
curl -sS -X POST https://swordfinder-production.up.railway.app/share/x/top-sword \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${SWORDFINDER_ADMIN_TOKEN}" \
  --data '{"date":"2026-05-06","dry_run":true}' | python3 -m json.tool
```

Expected signals:

- `post_mode` is `video`
- `media_upload_enabled` is `true`
- `video_url` is present
- `dry_run` is `true`

Post the native video:

```bash
source ~/.luna/secrets/keys.env
curl -sS --max-time 180 \
  -X POST https://swordfinder-production.up.railway.app/share/x/top-sword \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${SWORDFINDER_ADMIN_TOKEN}" \
  --data '{"date":"2026-05-06"}' | python3 -m json.tool
```

Expected success signals:

- `posted` is `true`
- `post_mode` is `video`
- `auth_mode` is `oauth1_user_token`
- `media.media_id` is present
- `url` points to the new X post

Check production auth status:

```bash
source ~/.luna/secrets/keys.env
curl -sS https://swordfinder-production.up.railway.app/share/x/oauth/status \
  -H "Authorization: Bearer ${SWORDFINDER_ADMIN_TOKEN}" | python3 -m json.tool
```

Expected native-video signal:

- `media_upload_enabled` is `true`

`media_write_scope` may still be `false`; that only describes OAuth2. Native video posting is allowed because the app has OAuth1 user tokens.

## Local Non-Posting Media Upload Check

This validates the OAuth1 upload path without creating a public X post.

```bash
source ~/.luna/secrets/keys.env
.venv/bin/python - <<'PY'
import asyncio
import api

VIDEO_URL = "https://swordfinderstorage.blob.core.windows.net/swordfinder-videos/swords/2026-05-06/sword_2026-05-06_De_los_Santos%2C_Yerry_32.0mph.mp4"

async def main():
    session = api.x_oauth1_env_session()
    video_bytes, media_type = await api.download_video_bytes(VIDEO_URL)
    media = await api.upload_x_video_bytes(video_bytes, media_type, session)
    print("upload_ok", bool(media.get("media_id")), media.get("media_type"))

asyncio.run(main())
PY
```

This uploads and finalizes media on X but does not create a post. X may keep the uploaded media temporarily.

## Implementation Notes

- Videos use chunked upload. Do not use simple media upload for MP4.
- `media_id_string` is the safe id to use when attaching media to a post.
- SwordFinder uses 4 MB chunks via `X_MEDIA_CHUNK_SIZE`.
- If `INIT` returns `403` with `media_category=tweet_video`, SwordFinder retries `INIT` without `media_category` for compatibility.
- If `FINALIZE` returns processing info, poll `STATUS` until `succeeded` or `failed`.
- For public posting, the backend must stay on Railway because it has the production secrets.

## Source Docs

- X OAuth 1.0a overview: https://docs.x.com/fundamentals/authentication/oauth-1-0a/overview
- X v1.1 chunked media upload: https://developer.x.com/en/docs/twitter-api/v1/media/upload-media/uploading-media/chunked-media-upload
- X media upload tutorial: https://developer.x.com/en/docs/tutorials/uploading-media
- X v2 media initialize reference: https://docs.x.com/x-api/media/initialize-media-upload
- X v2 create post reference: https://docs.x.com/x-api/posts/create-post
