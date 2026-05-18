import {
  escapeHtml,
  fetchRows,
  formatDate,
  latestSeasonRange,
  linkForPitcher,
  linkForPlayer,
} from './supabase-rest.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav('leaderboards');
setFooter();

const cardsRoot = document.getElementById('leaderboard-cards');
const hitterTableBody = document.getElementById('hitter-table-body');
const pitcherTableBody = document.getElementById('pitcher-table-body');
const heading = document.getElementById('leaderboard-heading');
const pitchTypeFilter = document.getElementById('pitch-type-filter');
const clearPitchFilterButton = document.getElementById('clear-pitch-filter');
const rangeButtons = Array.from(document.querySelectorAll('[data-range]'));

const season = latestSeasonRange();
let latestDate = null;
let activeRange = 'week';
let activePitchType = '';
let pitchTypeLabels = new Map();

function normalizePitchType(value) {
  const normalized = String(value || '').trim().toUpperCase();
  return /^[A-Z0-9_]{1,8}$/.test(normalized) ? normalized : '';
}

function setActiveRange(range) {
  activeRange = ['week', 'month', 'season'].includes(range) ? range : 'week';
  rangeButtons.forEach((btn) => {
    const isActive = btn.dataset.range === activeRange;
    btn.classList.toggle('primary', isActive);
    btn.classList.toggle('secondary', !isActive);
  });
}

function updateUrlState() {
  const url = new URL(window.location.href);
  if (activeRange === 'week') {
    url.searchParams.delete('range');
  } else {
    url.searchParams.set('range', activeRange);
  }

  if (activePitchType) {
    url.searchParams.set('pitch_type', activePitchType);
  } else {
    url.searchParams.delete('pitch_type');
  }

  window.history.replaceState({}, '', url);
}

function pitchTypeLabel(code) {
  if (!code) return 'All pitch types';
  const names = pitchTypeLabels.get(code);
  if (!names?.length) return code;
  return `${code} - ${names.slice(0, 2).join(' / ')}`;
}

function rangeStart() {
  if (!latestDate) return season.startDate;
  const latest = new Date(`${latestDate}T00:00:00`);
  const start = new Date(latest);

  if (activeRange === 'week') {
    start.setDate(start.getDate() - 6);
  } else if (activeRange === 'month') {
    start.setDate(start.getDate() - 29);
  } else {
    return season.startDate;
  }

  return start.toISOString().split('T')[0];
}

function renderTopSwordCards(rows) {
  cardsRoot.innerHTML = rows
    .slice(0, 8)
    .map(
      (row) => {
        const pitch = row.pitch_name || row.pitch_type || '--';
        const pitchCode = row.pitch_type && row.pitch_name ? ` (${row.pitch_type})` : '';
        return `
      <article class="card sword-card p-3 md:p-4">
        <div class="mb-2 flex items-center justify-between">
          <a class="font-semibold hover:text-[var(--accent-soft)]" href="${linkForPlayer(row)}">${escapeHtml(row.batter_name || 'Unknown')}</a>
          <span class="text-lg text-[var(--accent-soft)]">${Number(row.sword_score || 0).toFixed(1)}</span>
        </div>
        <p class="text-xs uppercase tracking-[0.08em] text-zinc-400">${formatDate(row.game_date)} • ${escapeHtml(pitch)}${escapeHtml(pitchCode)} ${Number(row.release_speed || 0).toFixed(1)} mph</p>
      </article>
    `;
      }
    )
    .join('');
}

function aggregateBy(rows, idKey, nameKey) {
  const map = new Map();

  rows.forEach((row) => {
    const id = row[idKey];
    const name = row[nameKey] || 'Unknown';
    if (!id) return;

    if (!map.has(id)) {
      map.set(id, {
        id,
        name,
        count: 0,
        totalScore: 0,
        bestScore: 0,
      });
    }

    const bucket = map.get(id);
    bucket.count += 1;
    bucket.totalScore += Number(row.sword_score || 0);
    bucket.bestScore = Math.max(bucket.bestScore, Number(row.sword_score || 0));
  });

  return Array.from(map.values()).map((item) => ({
    ...item,
    avgScore: item.count ? item.totalScore / item.count : 0,
  }));
}

function renderHitterTable(rows) {
  const hitters = aggregateBy(rows, 'batter', 'batter_name')
    .sort((a, b) => b.count - a.count || b.avgScore - a.avgScore)
    .slice(0, 12);

  hitterTableBody.innerHTML = hitters
    .map(
      (h, i) => `
      <tr class="border-b border-zinc-800">
        <td class="py-2 pr-2 text-zinc-400">${i + 1}</td>
        <td class="py-2 pr-2"><a class="hover:text-[var(--accent-soft)]" href="/player/${h.id}">${escapeHtml(h.name)}</a></td>
        <td class="py-2 pr-2 text-right">${h.count}</td>
        <td class="py-2 pr-2 text-right">${h.avgScore.toFixed(1)}</td>
        <td class="py-2 text-right text-[var(--accent-soft)]">${h.bestScore.toFixed(1)}</td>
      </tr>
    `
    )
    .join('');
}

function renderPitcherTable(rows) {
  const pitchers = aggregateBy(rows, 'pitcher', 'pitcher_name')
    .sort((a, b) => b.count - a.count || b.avgScore - a.avgScore)
    .slice(0, 12);

  pitcherTableBody.innerHTML = pitchers
    .map(
      (p, i) => `
      <tr class="border-b border-zinc-800">
        <td class="py-2 pr-2 text-zinc-400">${i + 1}</td>
        <td class="py-2 pr-2"><a class="hover:text-[var(--accent-soft)]" href="${linkForPitcher({ pitcher: p.id })}">${escapeHtml(p.name)}</a></td>
        <td class="py-2 pr-2 text-right">${p.count}</td>
        <td class="py-2 pr-2 text-right">${p.avgScore.toFixed(1)}</td>
        <td class="py-2 text-right text-[var(--accent-soft)]">${p.bestScore.toFixed(1)}</td>
      </tr>
    `
    )
    .join('');
}

async function fetchLatestDate() {
  const rows = await fetchRows('mlb_pitches_enhanced', {
    select: 'game_date',
    game_type: 'eq.R',
    sword_score: 'gte.90',
    game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    order: 'game_date.desc',
    limit: 1,
  });
  latestDate = rows[0]?.game_date || null;
}

async function fetchPitchTypeOptions() {
  const pageSize = 1000;
  const rows = [];
  for (let offset = 0; offset < 10000; offset += pageSize) {
    const page = await fetchRows('mlb_pitches_enhanced', {
      select: 'pitch_type,pitch_name',
      game_type: 'eq.R',
      sword_score: 'gte.90',
      pitch_type: 'not.is.null',
      game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
      order: 'pitch_type.asc,pitch_name.asc',
      limit: pageSize,
      offset,
    });
    rows.push(...page);
    if (page.length < pageSize) break;
  }
  const buckets = new Map();

  rows.forEach((row) => {
    const code = normalizePitchType(row.pitch_type);
    if (!code) return;
    if (!buckets.has(code)) buckets.set(code, new Set());
    const name = String(row.pitch_name || '').trim();
    if (name && name.toUpperCase() !== code) {
      buckets.get(code).add(name);
    }
  });

  pitchTypeLabels = new Map(
    Array.from(buckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([code, names]) => [code, Array.from(names).sort()])
  );

  const optionCodes = Array.from(pitchTypeLabels.keys());
  if (activePitchType && !pitchTypeLabels.has(activePitchType)) {
    optionCodes.unshift(activePitchType);
  }

  pitchTypeFilter.innerHTML = [
    '<option value="">All pitch types</option>',
    ...optionCodes.map(
      (code) => `<option value="${escapeHtml(code)}">${escapeHtml(pitchTypeLabel(code))}</option>`
    ),
  ].join('');
  pitchTypeFilter.value = activePitchType;
}

async function refresh() {
  if (!latestDate) {
    setStatusText('No leaderboard data available yet for this season.');
    cardsRoot.innerHTML = '';
    hitterTableBody.innerHTML = '';
    pitcherTableBody.innerHTML = '';
    return;
  }

  const start = rangeStart();
  const params = {
    select: 'id,batter,pitcher,player_name,pitcher_name,batter_name,sword_score,game_date,pitch_type,pitch_name,release_speed',
    game_type: 'eq.R',
    sword_score: 'gte.90',
    game_date: [`gte.${start}`, `lte.${latestDate}`],
    order: 'sword_score.desc',
    limit: 500,
  };
  if (activePitchType) {
    params.pitch_type = `eq.${activePitchType}`;
  }

  const rows = await fetchRows('mlb_pitches_enhanced', params);

  renderTopSwordCards(rows);
  renderHitterTable(rows);
  renderPitcherTable(rows);

  const rangeLabel = activeRange === 'season' ? `${season.year} season` : `last ${activeRange === 'week' ? '7' : '30'} days`;
  const pitchLabel = activePitchType ? `${pitchTypeLabel(activePitchType)} swords` : 'all pitch types';
  heading.textContent = activePitchType ? `Top ${activePitchType} Sword Events` : 'Top Sword Events';

  if (!rows.length) {
    setStatusText(`No ${pitchLabel} found for ${rangeLabel}.`);
    return;
  }

  setStatusText(`Showing ${pitchLabel} for ${rangeLabel} ending ${formatDate(latestDate)}.`);
}

rangeButtons.forEach((btn) => {
  btn.addEventListener('click', async () => {
    setActiveRange(btn.dataset.range);
    updateUrlState();
    await refresh();
  });
});

pitchTypeFilter.addEventListener('change', async () => {
  activePitchType = normalizePitchType(pitchTypeFilter.value);
  pitchTypeFilter.value = activePitchType;
  if (activePitchType) setActiveRange('season');
  updateUrlState();
  await refresh();
});

clearPitchFilterButton.addEventListener('click', async () => {
  activePitchType = '';
  pitchTypeFilter.value = '';
  updateUrlState();
  await refresh();
});

async function init() {
  try {
    setStatusText('Loading leaderboard data');
    const params = new URLSearchParams(window.location.search);
    setActiveRange(params.get('range') || activeRange);
    activePitchType = normalizePitchType(params.get('pitch_type') || params.get('pitch'));
    await fetchLatestDate();
    await fetchPitchTypeOptions();
    await refresh();
  } catch (error) {
    console.error(error);
    setStatusText(`Leaderboard load failed: ${error.message}`);
  }
}

init();
