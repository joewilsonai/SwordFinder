const cfg = window.SWORDFINDER_CONFIG || {};
const API_BASE_URL = (cfg.apiBaseUrl || '').replace(/\/$/, '');

const SUPABASE_URL = (cfg.supabaseUrl || '').replace(/\/$/, '');
const SUPABASE_ANON_KEY = cfg.supabaseAnonKey || '';

if (!API_BASE_URL && (!SUPABASE_URL || !SUPABASE_ANON_KEY)) {
  // Keep UI renderable even if config is missing.
  console.error('Missing SWORDFINDER_CONFIG.supabaseUrl or supabaseAnonKey');
}

const BASE_HEADERS = {
  apikey: SUPABASE_ANON_KEY,
  Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
};

function asList(value) {
  return Array.isArray(value) ? value : [value];
}

function buildQuery(params = {}) {
  const search = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    asList(value).forEach((single) => search.append(key, String(single)));
  });

  return search.toString();
}

export async function fetchRows(table, params = {}, options = {}) {
  if (API_BASE_URL) {
    const query = buildQuery({ table, ...params });
    const url = `${API_BASE_URL}/data/rows${query ? `?${query}` : ''}`;
    const response = await fetch(url, {
      method: 'GET',
      signal: options.signal,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`API rows request failed (${response.status}): ${text}`);
    }
    return response.json();
  }

  const query = buildQuery(params);
  const headers = { ...BASE_HEADERS, ...(options.headers || {}) };
  const url = `${SUPABASE_URL}/rest/v1/${table}${query ? `?${query}` : ''}`;

  const response = await fetch(url, {
    method: 'GET',
    headers,
    signal: options.signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Supabase request failed (${response.status}): ${text}`);
  }

  return response.json();
}

export async function fetchCount(table, params = {}, options = {}) {
  if (API_BASE_URL) {
    const query = buildQuery({ table, ...params });
    const url = `${API_BASE_URL}/data/count${query ? `?${query}` : ''}`;
    const response = await fetch(url, {
      method: 'GET',
      signal: options.signal,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`API count request failed (${response.status}): ${text}`);
    }
    const payload = await response.json();
    const total = Number(payload?.count ?? 0);
    return Number.isFinite(total) ? total : 0;
  }

  const query = buildQuery(params);
  const headers = {
    ...BASE_HEADERS,
    Prefer: 'count=exact',
    Range: '0-0',
    ...(options.headers || {}),
  };

  const url = `${SUPABASE_URL}/rest/v1/${table}${query ? `?${query}` : ''}`;
  const response = await fetch(url, {
    method: 'GET',
    headers,
    signal: options.signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Supabase count failed (${response.status}): ${text}`);
  }

  const range = response.headers.get('content-range') || '';
  const total = Number(range.split('/')[1] || 0);
  return Number.isFinite(total) ? total : 0;
}

export async function fetchOpsJson(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error('SwordFinder API base URL is required for ops endpoints');
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const response = await fetch(`${API_BASE_URL}${normalizedPath}`, {
    method: 'GET',
    signal: options.signal,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ops request failed (${response.status}): ${text}`);
  }

  return response.json();
}

export function formatDate(value) {
  if (!value) return 'Unknown date';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
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

export function bindVideoHover(root = document) {
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

  if (idx !== -1 && parts[idx + 1] && parts[idx + 1] !== `[id].html`) {
    return parts[idx + 1].replace('.html', '');
  }

  const param = new URLSearchParams(window.location.search).get('id');
  if (param) return param;

  return null;
}

export function latestSeasonRange() {
  const year = Number((window.SWORDFINDER_CONFIG || {}).seasonYear || new Date().getFullYear());
  return {
    year,
    startDate: `${year}-01-01`,
    endDate: `${year + 1}-01-01`,
  };
}
