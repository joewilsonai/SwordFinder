const DEFAULT_API_BASE_URL = 'https://swordfinder-production.up.railway.app';
const DEFAULT_PUBLIC_BASE_URL = 'https://swordfinder.com';

function cleanBaseUrl(value, fallback) {
  return String(value || fallback).replace(/\/$/, '');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatStat(value, decimals = 1, fallback = '--') {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(decimals) : fallback;
}

function normalizeRank(value) {
  const rank = Number.parseInt(value, 10);
  if (!Number.isFinite(rank)) return 1;
  return Math.min(Math.max(rank, 1), 5);
}

function validateDate(value) {
  const date = String(value || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    const error = new Error('date must use YYYY-MM-DD');
    error.statusCode = 400;
    throw error;
  }
  return date;
}

function cardTitle({ rank, row }) {
  const hitter = row.batter_name || row.player_name || 'Unknown hitter';
  return `SwordFinder #${rank}: ${hitter}`;
}

function cardDescription(row) {
  const pitcher = row.pitcher_name || 'Unknown pitcher';
  const pitch = row.pitch_name || row.pitch_type || 'Pitch';
  const releaseSpeed = formatStat(row.release_speed);
  const score = formatStat(row.sword_score);
  const batSpeed = formatStat(row.bat_speed);
  const miss = formatStat(row.strike_zone_distance_inches);
  return `Score ${score}. ${pitch} ${releaseSpeed} mph vs ${pitcher}. Bat ${batSpeed} mph, miss ${miss} in.`;
}

function brandImageUrl(baseUrl) {
  return `${cleanBaseUrl(baseUrl, DEFAULT_PUBLIC_BASE_URL)}/assets/brand/swordfinder-wordmark.png`;
}

function buildPlayerUrl({ date, rank, baseUrl }) {
  const base = cleanBaseUrl(baseUrl, DEFAULT_PUBLIC_BASE_URL);
  const params = new URLSearchParams({ date, rank: String(normalizeRank(rank)), mode: 'player' });
  return `${base}/api/watch/top-sword?${params.toString()}`;
}

function buildCanonicalUrl({ date, rank, baseUrl }) {
  const base = cleanBaseUrl(baseUrl, DEFAULT_PUBLIC_BASE_URL);
  const params = new URLSearchParams({ date, rank: String(normalizeRank(rank)) });
  return `${base}/api/watch/top-sword?${params.toString()}`;
}

function buildCardHtml({ date, rank = 1, row, baseUrl }) {
  const safeDate = validateDate(date);
  const safeRank = normalizeRank(rank);
  const publicBaseUrl = cleanBaseUrl(baseUrl, DEFAULT_PUBLIC_BASE_URL);
  const videoUrl = row?.video_azure_blob_url;
  if (!videoUrl) {
    const error = new Error('Top sword video is not available yet');
    error.statusCode = 409;
    throw error;
  }

  const title = cardTitle({ rank: safeRank, row });
  const description = cardDescription(row);
  const playerUrl = buildPlayerUrl({ date: safeDate, rank: safeRank, baseUrl: publicBaseUrl });
  const canonicalUrl = buildCanonicalUrl({ date: safeDate, rank: safeRank, baseUrl: publicBaseUrl });
  const imageUrl = brandImageUrl(publicBaseUrl);

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <meta name="description" content="${escapeHtml(description)}" />
  <link rel="canonical" href="${escapeHtml(canonicalUrl)}" />
  <meta name="twitter:card" content="player" />
  <meta name="twitter:site" content="@joewilsonai" />
  <meta name="twitter:title" content="${escapeHtml(title)}" />
  <meta name="twitter:description" content="${escapeHtml(description)}" />
  <meta name="twitter:image" content="${escapeHtml(imageUrl)}" />
  <meta name="twitter:image:alt" content="SwordFinder logo" />
  <meta name="twitter:player" content="${escapeHtml(playerUrl)}" />
  <meta name="twitter:player:width" content="1280" />
  <meta name="twitter:player:height" content="720" />
  <meta name="twitter:player:stream" content="${escapeHtml(videoUrl)}" />
  <meta name="twitter:player:stream:content_type" content="video/mp4" />
  <meta property="og:type" content="video.other" />
  <meta property="og:title" content="${escapeHtml(title)}" />
  <meta property="og:description" content="${escapeHtml(description)}" />
  <meta property="og:image" content="${escapeHtml(imageUrl)}" />
  <meta property="og:url" content="${escapeHtml(canonicalUrl)}" />
  <meta property="og:video" content="${escapeHtml(videoUrl)}" />
  <meta property="og:video:type" content="video/mp4" />
</head>
<body style="margin:0;background:#050505;color:#f4f4f5;font-family:Arial,sans-serif;">
  <a href="${escapeHtml(playerUrl)}" style="display:block;padding:24px;color:#f4f4f5;">Watch ${escapeHtml(title)}</a>
</body>
</html>`;
}

function buildPlayerHtml({ date, rank = 1, row, baseUrl }) {
  const safeDate = validateDate(date);
  const safeRank = normalizeRank(rank);
  const publicBaseUrl = cleanBaseUrl(baseUrl, DEFAULT_PUBLIC_BASE_URL);
  const videoUrl = row?.video_azure_blob_url;
  if (!videoUrl) {
    const error = new Error('Top sword video is not available yet');
    error.statusCode = 409;
    throw error;
  }

  const title = cardTitle({ rank: safeRank, row });
  const canonicalUrl = buildCanonicalUrl({ date: safeDate, rank: safeRank, baseUrl: publicBaseUrl });
  const imageUrl = brandImageUrl(publicBaseUrl);

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)} | SwordFinder</title>
  <style>
    html, body { margin: 0; width: 100%; height: 100%; background: #000; }
    video { display: block; width: 100vw; height: 100vh; object-fit: contain; background: #000; }
  </style>
</head>
<body>
  <video controls autoplay muted playsinline preload="metadata" poster="${escapeHtml(imageUrl)}">
    <source src="${escapeHtml(videoUrl)}" type="video/mp4" />
    <a href="${escapeHtml(canonicalUrl)}">Watch on SwordFinder</a>
  </video>
</body>
</html>`;
}

async function fetchTopSword({ date, rank, apiBaseUrl }) {
  const safeDate = validateDate(date);
  const safeRank = normalizeRank(rank);
  const apiBase = cleanBaseUrl(apiBaseUrl, DEFAULT_API_BASE_URL);
  const params = new URLSearchParams({
    date: safeDate,
    limit: String(safeRank),
    ensure_videos: 'true',
  });
  const response = await fetch(`${apiBase}/daily-slate?${params.toString()}`);
  if (!response.ok) {
    const error = new Error(`SwordFinder API request failed (${response.status})`);
    error.statusCode = 502;
    throw error;
  }
  const payload = await response.json();
  const row = payload.rows?.[safeRank - 1];
  if (!row) {
    const error = new Error('No sword found for this date');
    error.statusCode = 404;
    throw error;
  }
  return row;
}

async function handler(req, res) {
  try {
    const date = validateDate(req.query.date);
    const rank = normalizeRank(req.query.rank || 1);
    const mode = req.query.mode === 'player' ? 'player' : 'card';
    const baseUrl = cleanBaseUrl(
      process.env.PUBLIC_UI_BASE_URL || process.env.UI_BASE_URL,
      DEFAULT_PUBLIC_BASE_URL,
    );
    const row = await fetchTopSword({
      date,
      rank,
      apiBaseUrl: process.env.SWORDFINDER_API_BASE_URL || process.env.API_BASE_URL,
    });
    const html = mode === 'player'
      ? buildPlayerHtml({ date, rank, row, baseUrl })
      : buildCardHtml({ date, rank, row, baseUrl });

    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=3600');
    res.status(200).send(html);
  } catch (error) {
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.status(error.statusCode || 500).send(error.message || 'Unable to render SwordFinder card');
  }
}

module.exports = handler;
module.exports.buildCardHtml = buildCardHtml;
module.exports.buildPlayerHtml = buildPlayerHtml;
module.exports.buildCanonicalUrl = buildCanonicalUrl;
module.exports.buildPlayerUrl = buildPlayerUrl;
