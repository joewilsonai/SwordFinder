import { filterRows, queryRows } from './query.js';

// All of SwordFinder's data is plain JSON in /data, rebuilt daily by pipeline/update.py.

async function loadJson(path, options = {}) {
  const response = await fetch(path, { signal: options.signal });
  if (!response.ok) {
    throw new Error(`Could not load ${path} (${response.status})`);
  }
  return response.json();
}

const STATUS = await loadJson('/data/status.json').catch(() => null);
const SEASON = Number(STATUS?.season || (window.SWORDFINDER_CONFIG || {}).seasonYear || new Date().getFullYear());
const cache = new Map();

function loadOnce(path) {
  if (!cache.has(path)) {
    cache.set(path, loadJson(path).catch((error) => {
      cache.delete(path);
      throw error;
    }));
  }
  return cache.get(path);
}

async function seasonRows() {
  const payload = await loadOnce(`/data/${SEASON}.json`);
  return payload.rows || [];
}

export function getStatus() {
  return STATUS;
}

export async function fetchRows(_table, params = {}) {
  return queryRows(await seasonRows(), params);
}

export async function fetchCount(_table, params = {}) {
  return filterRows(await seasonRows(), params).length;
}

function missingClips(rows) {
  return rows.filter((row) => !row.video_azure_blob_url && !row.clip_unavailable).length;
}

export async function fetchApiJson(path, params = {}) {
  if (path === '/daily-slate') {
    const rows = queryRows(await seasonRows(), {
      game_date: `eq.${params.date}`,
      order: 'sword_score.desc',
      limit: params.limit || 5,
    });
    return { date: params.date, count: rows.length, hydrated: 0, pending_videos: missingClips(rows), rows };
  }

  const profile = path.match(/^\/profiles\/(batter|pitcher)\/(\d+)\/swords$/);
  if (profile) {
    const [, kind, id] = profile;
    const [rows, totals] = await Promise.all([seasonRows(), loadOnce(`/data/${SEASON}-totals.json`)]);
    const found = queryRows(rows, {
      [kind]: `eq.${id}`,
      order: 'sword_score.desc',
      limit: params.limit || 80,
    });
    return {
      profile_kind: kind,
      entity_id: Number(id),
      count: found.length,
      total_pitches: Number(totals?.[kind]?.[id] || 0),
      hydrated: 0,
      pending_videos: missingClips(found),
      rows: found,
    };
  }

  throw new Error(`No data file for ${path}`);
}

export function formatDate(value) {
  if (!value) return 'Unknown date';

  const dateOnly = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) {
    const [, year, month, day] = dateOnly;
    return new Date(Number(year), Number(month) - 1, Number(day)).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }

  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatApiTimestamp(value) {
  if (!value) return '--';

  const raw = String(value);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw);
  const looksLikeIsoDateTime = /^\d{4}-\d{2}-\d{2}T/.test(raw);
  const normalized = looksLikeIsoDateTime && !hasTimezone ? `${raw}Z` : raw;
  const dt = new Date(normalized);

  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatCompact(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--';
  }
  return Intl.NumberFormat('en-US', { notation: 'compact' }).format(Number(value));
}

export function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value || '';
  return div.innerHTML;
}

export function videoPreviewUrl(value, seconds = 0.25) {
  const url = String(value || '').trim();
  if (!url || url.includes('#')) return url;
  return `${url}#t=${seconds}`;
}

export function linkForPlayer(row) {
  const id = row?.batter;
  if (!id) return '#';
  return `/player/${id}`;
}

export function linkForPitcher(row) {
  const id = row?.pitcher;
  if (!id) return '#';
  return `/pitcher/${id}`;
}

export function linkForSword(row) {
  const id = row?.id;
  if (!id) return '#';
  return `/sword/${id}`;
}

// A clip can run 8 MB, so nothing downloads until it's on screen, and it pauses once it scrolls away.
const playOnScreen = 'IntersectionObserver' in window
  ? new IntersectionObserver((entries) => {
    entries.forEach(({ target, isIntersecting }) => {
      if (isIntersecting) {
        target.play().catch(() => {});
      } else {
        target.pause();
      }
    });
  }, { threshold: 0.5 })
  : null;

export function bindVideoHover(root = document) {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (playOnScreen && !reducedMotion) {
    root.querySelectorAll('video[data-play-on-screen="true"]').forEach((video) => playOnScreen.observe(video));
  }

  root.querySelectorAll('video[data-hover-unmute="true"]').forEach((video) => {
    video.addEventListener('mouseenter', () => {
      video.muted = false;
    });

    video.addEventListener('mouseleave', () => {
      video.muted = true;
      video.volume = 1;
    });
  });
}

export function parseEntityIdFromPath(kind) {
  const path = window.location.pathname.replace(/\/$/, '');
  const parts = path.split('/').filter(Boolean);
  const idx = parts.indexOf(kind);

  const nextPart = parts[idx + 1];
  if (
    idx !== -1 &&
    nextPart &&
    !['[id].html', 'profile', 'profile.html'].includes(nextPart)
  ) {
    return nextPart.replace('.html', '');
  }

  const param = new URLSearchParams(window.location.search).get('id');
  if (param) return param;

  return null;
}

export function latestSeasonRange() {
  const year = SEASON;
  return {
    year,
    startDate: `${year}-01-01`,
    endDate: `${year + 1}-01-01`,
  };
}
