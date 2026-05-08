import {
  escapeHtml,
  fetchCount,
  fetchOpsJson,
  fetchRows,
  formatCompact,
  formatDate,
  latestSeasonRange,
} from './supabase-rest.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav('ops');
setFooter();

const dateInput = document.getElementById('ops-date-input');
const refreshButton = document.getElementById('ops-refresh');
const dateLabel = document.getElementById('ops-date-label');
const healthPill = document.getElementById('ops-health-pill');
const healthDetail = document.getElementById('ops-health-detail');
const lastChecked = document.getElementById('ops-last-checked');
const metricRoot = document.getElementById('ops-metrics');
const seasonRoot = document.getElementById('season-metrics');
const pendingList = document.getElementById('pending-list');
const pendingEmpty = document.getElementById('pending-empty');
const pendingCountPill = document.getElementById('pending-count-pill');
const commandBlock = document.getElementById('ops-command');

const season = latestSeasonRange();

function percent(value) {
  const number = Number(value || 0) * 100;
  return `${number.toFixed(number >= 10 ? 0 : 1)}%`;
}

function formatTimestamp(value) {
  if (!value) return '--';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function metricTile(label, value, detail = '') {
  return `
    <article class="metric-tile p-4">
      <p class="text-xs uppercase tracking-[0.12em] text-zinc-500">${escapeHtml(label)}</p>
      <p class="mt-2 text-3xl font-semibold leading-none">${escapeHtml(value)}</p>
      ${detail ? `<p class="mt-2 text-sm text-zinc-400">${escapeHtml(detail)}</p>` : ''}
    </article>
  `;
}

function compactRow(label, value, detail = '') {
  return `
    <div class="flex items-center justify-between gap-4 rounded-md border border-zinc-800 bg-black/30 px-3 py-2">
      <div>
        <p class="text-sm text-zinc-300">${escapeHtml(label)}</p>
        ${detail ? `<p class="text-xs text-zinc-500">${escapeHtml(detail)}</p>` : ''}
      </div>
      <p class="text-lg font-semibold text-[var(--accent-soft)]">${escapeHtml(value)}</p>
    </div>
  `;
}

function renderHealth(health) {
  const connected = health?.status === 'healthy' && health?.database === 'connected';
  healthPill.textContent = connected ? 'Healthy' : 'Needs Check';
  healthPill.classList.toggle('is-good', connected);
  healthPill.classList.toggle('is-bad', !connected);
  healthDetail.textContent = connected ? 'Database connected' : 'API issue detected';
  lastChecked.textContent = `Checked ${formatTimestamp(health?.timestamp)}`;
}

function renderSlate(status) {
  metricRoot.innerHTML = [
    metricTile('Slate Swords', formatCompact(status.total_swords), formatDate(status.date)),
    metricTile('Cached Videos', formatCompact(status.cached_videos), `${percent(status.cache_rate)} cache rate`),
    metricTile('Pending Videos', formatCompact(status.pending_videos), 'Missing Azure clip URL'),
    metricTile('Top Queue', formatCompact(status.top_pending?.length || 0), 'Rows returned by API'),
  ].join('');

  dateLabel.textContent = `Viewing ${formatDate(status.date)}`;
  pendingCountPill.textContent = `${status.pending_videos} pending`;
  commandBlock.textContent = `python process_daily_sword_videos.py --date ${status.date} --top-n 25`;
}

function renderSeason(total, cached) {
  const pending = Math.max(total - cached, 0);
  const rate = total ? cached / total : 0;
  seasonRoot.innerHTML = [
    compactRow('Season swords', formatCompact(total), `${season.year} regular data`),
    compactRow('Season cached', formatCompact(cached), `${percent(rate)} cache rate`),
    compactRow('Season pending', formatCompact(pending), 'Uncached sword rows'),
  ].join('');
}

function pendingTemplate(row, index) {
  const score = Number(row.sword_score || 0).toFixed(1);
  const batSpeed = row.bat_speed ? `${Number(row.bat_speed).toFixed(1)} mph` : '--';
  const miss = row.strike_zone_distance_inches !== null && row.strike_zone_distance_inches !== undefined
    ? `${Number(row.strike_zone_distance_inches).toFixed(1)} in`
    : '--';

  return `
    <div class="grid gap-3 py-3 md:grid-cols-[40px_1fr_auto] md:items-center">
      <p class="text-sm text-zinc-500">#${index + 1}</p>
      <div>
        <p class="text-lg font-semibold">
          ${escapeHtml(row.batter_name || 'Unknown hitter')}
          <span class="text-sm font-normal text-zinc-500">vs</span>
          ${escapeHtml(row.pitcher_name || row.source_player_name || 'Unknown pitcher')}
        </p>
        <p class="text-sm text-zinc-400">
          ${escapeHtml(row.pitch_name || row.pitch_type || 'Pitch')} / ${escapeHtml(row.description || 'swinging strike')}
        </p>
      </div>
      <div class="grid grid-cols-3 gap-2 text-right text-sm md:min-w-[250px]">
        <span><strong class="block text-[var(--accent-soft)]">${score}</strong><span class="text-zinc-500">score</span></span>
        <span><strong class="block text-zinc-200">${batSpeed}</strong><span class="text-zinc-500">bat</span></span>
        <span><strong class="block text-zinc-200">${miss}</strong><span class="text-zinc-500">miss</span></span>
      </div>
    </div>
  `;
}

function renderPending(rows) {
  if (!rows.length) {
    pendingList.innerHTML = '';
    pendingEmpty.classList.remove('hidden');
    return;
  }

  pendingEmpty.classList.add('hidden');
  pendingList.innerHTML = rows.map(pendingTemplate).join('');
}

async function fetchLatestDate() {
  const rows = await fetchRows('mlb_pitches_enhanced', {
    select: 'game_date',
    sword_score: 'gt.0',
    game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    order: 'game_date.desc',
    limit: 1,
  });
  return rows[0]?.game_date || null;
}

async function fetchSeasonCounts() {
  const [total, cached] = await Promise.all([
    fetchCount('mlb_pitches_enhanced', {
      select: 'id',
      sword_score: 'gt.0',
      game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    }),
    fetchCount('mlb_pitches_enhanced', {
      select: 'id',
      sword_score: 'gt.0',
      video_azure_blob_url: 'not.is.null',
      game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    }),
  ]);
  return { total, cached };
}

async function refreshOps(date) {
  setStatusText(`Loading operations data for ${formatDate(date)}`);
  refreshButton.disabled = true;
  refreshButton.textContent = 'Loading';

  try {
    const encodedDate = encodeURIComponent(date);
    const [health, status, backlog, seasonCounts] = await Promise.all([
      fetchOpsJson('/health'),
      fetchOpsJson(`/ops/video-backlog/status?date=${encodedDate}&limit=6`),
      fetchOpsJson(`/ops/video-backlog?date=${encodedDate}&limit=12`),
      fetchSeasonCounts(),
    ]);

    renderHealth(health);
    renderSlate(status);
    renderSeason(seasonCounts.total, seasonCounts.cached);
    renderPending(backlog.pending || status.top_pending || []);
    setStatusText(`Operations current for ${formatDate(date)}.`);
  } catch (error) {
    console.error(error);
    setStatusText(`Ops load failed: ${error.message}`);
    healthPill.textContent = 'Error';
    healthPill.classList.remove('is-good');
    healthPill.classList.add('is-bad');
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = 'Refresh';
  }
}

refreshButton.addEventListener('click', () => {
  if (dateInput.value) {
    refreshOps(dateInput.value);
  }
});

async function init() {
  try {
    const latestDate = await fetchLatestDate();
    if (!latestDate) {
      setStatusText(`No ${season.year} sword data found.`);
      return;
    }

    dateInput.value = latestDate;
    dateInput.max = latestDate;
    await refreshOps(latestDate);
  } catch (error) {
    console.error(error);
    setStatusText(`Ops load failed: ${error.message}`);
  }
}

init();
