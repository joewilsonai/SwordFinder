import {
  bindVideoHover,
  escapeHtml,
  fetchRows,
  formatDate,
  latestSeasonRange,
  linkForPitcher,
  linkForPlayer,
  linkForSword,
  videoPreviewUrl,
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
const pitchFamilyRail = document.getElementById('pitch-family-rail');
const pitchTypeChipList = document.getElementById('pitch-type-chip-list');
const boardViewTabs = document.getElementById('leaderboard-view-tabs');
const rangeButtons = Array.from(document.querySelectorAll('[data-range]'));

const season = latestSeasonRange();
let latestDate = null;
let activeRange = 'week';
let activePitchFilter = '';
let activeBoardView = 'pitch-types';
let pitchTypeLabels = new Map();

const PITCH_FAMILIES = [
  {
    id: 'fastballs',
    label: 'Fastballs',
    codes: ['FF', 'FA', 'SI', 'FC'],
  },
  {
    id: 'breaking',
    label: 'Breaking Balls',
    codes: ['SL', 'ST', 'CU', 'KC', 'SV', 'CS'],
  },
  {
    id: 'offspeed',
    label: 'Offspeed',
    codes: ['CH', 'FS', 'FO', 'SC'],
  },
];

const PITCH_FAMILY_BY_ID = new Map(PITCH_FAMILIES.map((family) => [family.id, family]));
const BOARD_VIEWS = new Set(['pitch-types', 'hitters', 'pitchers']);

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

function normalizeBoardView(value) {
  const view = String(value || '').trim().toLowerCase();
  return BOARD_VIEWS.has(view) ? view : 'pitch-types';
}

function setActiveBoardView(value) {
  activeBoardView = normalizeBoardView(value);
  boardViewTabs?.querySelectorAll('[data-board-view]').forEach((button) => {
    const isActive = button.dataset.boardView === activeBoardView;
    button.classList.toggle('primary', isActive);
    button.classList.toggle('secondary', !isActive);
  });
}

function activePitchType() {
  return activePitchFilter.startsWith('pitch:') ? normalizePitchType(activePitchFilter.slice(6)) : '';
}

function activePitchFamily() {
  if (!activePitchFilter.startsWith('family:')) return null;
  return PITCH_FAMILY_BY_ID.get(activePitchFilter.slice(7)) || null;
}

function updateUrlState() {
  const url = new URL(window.location.href);
  if (activeRange === 'week') {
    url.searchParams.delete('range');
  } else {
    url.searchParams.set('range', activeRange);
  }

  const pitchType = activePitchType();
  const pitchFamily = activePitchFamily();

  if (pitchType) {
    url.searchParams.set('pitch_type', pitchType);
    url.searchParams.delete('pitch_group');
  } else if (pitchFamily) {
    url.searchParams.set('pitch_group', pitchFamily.id);
    url.searchParams.delete('pitch_type');
  } else {
    url.searchParams.delete('pitch_type');
    url.searchParams.delete('pitch_group');
  }

  if (activeBoardView === 'pitch-types') {
    url.searchParams.delete('view');
  } else {
    url.searchParams.set('view', activeBoardView);
  }

  window.history.replaceState({}, '', url);
}

function pitchTypeLabel(code) {
  if (!code) return 'All pitch types';
  const names = pitchTypeLabels.get(code);
  if (!names?.length) return code;
  return `${code} - ${names.slice(0, 2).join(' / ')}`;
}

function pitchTypeHeading(code) {
  const label = pitchTypeLabel(code);
  return label.includes(' - ') ? label.split(' - ')[1] : label;
}

function availablePitchCodes() {
  return Array.from(pitchTypeLabels.keys());
}

function selectedPitchCodes(rows = []) {
  const pitchType = activePitchType();
  if (pitchType) return [pitchType];

  const rowCodes = new Set(
    rows
      .map((row) => normalizePitchType(row.pitch_type))
      .filter(Boolean)
  );
  const knownCodes = availablePitchCodes().filter((code) => rowCodes.has(code) || !rowCodes.size);
  const family = activePitchFamily();

  if (family) {
    return family.codes.filter((code) => knownCodes.includes(code) || rowCodes.has(code));
  }

  return knownCodes.length ? knownCodes : Array.from(rowCodes).sort();
}

function activePitchLabel() {
  const pitchType = activePitchType();
  if (pitchType) return pitchTypeLabel(pitchType);
  const family = activePitchFamily();
  return family ? family.label : 'all pitch types';
}

function normalizePitchFilter(rawValue) {
  const value = String(rawValue || '');
  if (value.startsWith('family:') && PITCH_FAMILY_BY_ID.has(value.slice(7))) {
    return value;
  }
  if (value.startsWith('pitch:')) {
    const code = normalizePitchType(value.slice(6));
    return code ? `pitch:${code}` : '';
  }
  return '';
}

function setActivePitchFilter(rawValue) {
  activePitchFilter = normalizePitchFilter(rawValue);
  pitchTypeFilter.value = activePitchFilter;
  updatePitchExplorerActiveState();
}

function updatePitchExplorerActiveState() {
  pitchFamilyRail?.querySelectorAll('[data-pitch-filter]').forEach((button) => {
    const isActive = button.dataset.pitchFilter === activePitchFilter;
    button.classList.toggle('primary', isActive);
    button.classList.toggle('secondary', !isActive);
  });
}

function renderPitchTypeChips() {
  if (!pitchTypeChipList) return;
  const codes = availablePitchCodes();

  if (!codes.length) {
    pitchTypeChipList.innerHTML = '<p class="text-sm text-zinc-500">Pitch type shortcuts load with the season data.</p>';
    return;
  }

  pitchTypeChipList.innerHTML = codes
    .map(
      (code) => `
        <button class="pitch-chip secondary rounded-md px-3 py-2 text-xs uppercase tracking-[0.08em]" type="button" data-pitch-filter="pitch:${escapeHtml(code)}">
          ${escapeHtml(pitchTypeLabel(code))}
        </button>
      `
    )
    .join('');
  updatePitchExplorerActiveState();
}

function bindPitchExplorer() {
  pitchFamilyRail?.addEventListener('click', async (event) => {
    const target = event.target.closest('[data-pitch-filter]');
    if (!target) return;
    setActivePitchFilter(target.dataset.pitchFilter);
    if (activePitchFilter) setActiveRange('season');
    updateUrlState();
    await refresh();
  });
}

function bindBoardViewTabs() {
  boardViewTabs?.addEventListener('click', async (event) => {
    const target = event.target.closest('[data-board-view]');
    if (!target) return;
    setActiveBoardView(target.dataset.boardView);
    if (activeBoardView !== 'pitch-types') setActiveRange('season');
    updateUrlState();
    await refresh();
  });
}

function shouldUseNativeTarget(target) {
  return Boolean(target.closest('a, button, input, label, select, textarea, video'));
}

function bindLeaderboardCardClicks() {
  cardsRoot?.addEventListener('click', (event) => {
    const card = event.target.closest('[data-sword-href]');
    if (!card || shouldUseNativeTarget(event.target)) return;
    window.location.href = card.dataset.swordHref;
  });

  cardsRoot?.addEventListener('keydown', (event) => {
    if (!['Enter', ' '].includes(event.key) || shouldUseNativeTarget(event.target)) return;
    const card = event.target.closest('[data-sword-href]');
    if (!card) return;
    event.preventDefault();
    window.location.href = card.dataset.swordHref;
  });
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

function renderLeaderboardVideo(row, className = '') {
  if (!row.video_azure_blob_url) {
    return `
      <div class="leaderboard-video video-shell ${className}">
        <div class="video-placeholder text-sm text-zinc-500">Video pending</div>
      </div>
    `;
  }

  const previewUrl = videoPreviewUrl(row.video_azure_blob_url);

  return `
    <div class="leaderboard-video video-shell ${className}">
      <video data-hover-unmute="true" muted playsinline controls preload="metadata">
        <source src="${escapeHtml(previewUrl)}" type="video/mp4" />
      </video>
    </div>
  `;
}

function renderSwordCard(row, rank, options = {}) {
  const { featured = false } = options;
  const pitch = row.pitch_name || row.pitch_type || '--';
  const pitchCode = row.pitch_type && row.pitch_name ? ` (${row.pitch_type})` : '';
  const cardClass = featured ? 'leaderboard-feature-card' : 'leaderboard-rank-card';
  const swordLink = linkForSword(row);
  const hitterName = row.batter_name || 'Unknown';

  return `
      <article class="${cardClass} clickable-sword-card card sword-card p-3 md:p-4" data-sword-href="${escapeHtml(swordLink)}" tabindex="0" role="link" aria-label="Open sword page">
        ${renderLeaderboardVideo(row, featured ? 'mb-4' : 'mb-3')}
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-xs uppercase tracking-[0.12em] text-zinc-500">#${rank} Sword</p>
            <a class="${featured ? 'text-3xl' : 'text-xl'} block truncate font-semibold leading-none hover:text-[var(--accent-soft)]" href="${linkForPlayer(row)}">${escapeHtml(hitterName)}</a>
          </div>
          <span class="${featured ? 'text-3xl' : 'text-2xl'} shrink-0 font-semibold text-[var(--accent-soft)]">${Number(row.sword_score || 0).toFixed(1)}</span>
        </div>
        <p class="mt-3 text-xs uppercase tracking-[0.08em] text-zinc-400">${formatDate(row.game_date)} • ${escapeHtml(pitch)}${escapeHtml(pitchCode)} ${Number(row.release_speed || 0).toFixed(1)} mph</p>
        <p class="mt-1 text-sm text-zinc-400">vs <a class="underline decoration-zinc-600 hover:decoration-[var(--accent-soft)]" href="${linkForPitcher(row)}">${escapeHtml(row.pitcher_name || row.player_name || 'Unknown pitcher')}</a></p>
        <div class="leaderboard-card-actions">
          <a class="primary rounded-md px-3 py-2 text-xs uppercase tracking-[0.08em]" href="${escapeHtml(swordLink)}">View Sword</a>
          <span class="text-xs uppercase tracking-[0.08em] text-zinc-500">Click card for clip</span>
        </div>
      </article>
    `;
}

function renderTopSwordCards(rows) {
  const codes = selectedPitchCodes(rows);
  const rowsByPitch = new Map(codes.map((code) => [code, []]));

  rows.forEach((row) => {
    const code = normalizePitchType(row.pitch_type);
    if (!rowsByPitch.has(code)) return;
    const group = rowsByPitch.get(code);
    if (group.length < 5) group.push(row);
  });

  const groups = codes
    .map((code) => ({
      code,
      rows: rowsByPitch.get(code) || [],
    }))
    .filter((group) => group.rows.length);

  if (!groups.length) {
    cardsRoot.className = 'grid gap-6';
    cardsRoot.innerHTML = '';
    return 0;
  }

  cardsRoot.className = 'grid gap-6';
  cardsRoot.innerHTML = groups
    .map(
      (group) => `
      <div class="pitch-type-group">
        <div class="mb-3 flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
          <div>
            <p class="text-xs uppercase tracking-[0.12em] text-zinc-500">${escapeHtml(group.code)}</p>
            <h3 class="brand-title text-3xl leading-none">${escapeHtml(pitchTypeHeading(group.code))}</h3>
          </div>
          <p class="text-sm text-zinc-400">Top ${group.rows.length} ${escapeHtml(group.code)} sword${group.rows.length === 1 ? '' : 's'}</p>
        </div>
        <div class="leaderboard-pitch-grid">
          ${renderSwordCard(group.rows[0], 1, { featured: true })}
          <div class="leaderboard-rank-grid">
            ${group.rows.slice(1).map((row, index) => renderSwordCard(row, index + 2)).join('')}
          </div>
        </div>
      </div>
    `
    )
    .join('');

  bindVideoHover(cardsRoot);
  return groups.reduce((total, group) => total + group.rows.length, 0);
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
        bestRow: null,
      });
    }

    const bucket = map.get(id);
    const score = Number(row.sword_score || 0);
    bucket.count += 1;
    bucket.totalScore += score;
    if (score >= bucket.bestScore) {
      bucket.bestScore = score;
      bucket.bestRow = row;
    }
  });

  return Array.from(map.values()).map((item) => ({
    ...item,
    avgScore: item.count ? item.totalScore / item.count : 0,
  }));
}

function renderProfileLeaderboardCard(item, rank, kind) {
  const isPitcher = kind === 'pitcher';
  const profileUrl = isPitcher ? linkForPitcher({ pitcher: item.id }) : `/player/${item.id}`;
  const topRow = item.bestRow || {};
  const topSwordUrl = linkForSword(topRow);
  const opponent = isPitcher
    ? topRow.batter_name || 'Unknown hitter'
    : topRow.pitcher_name || topRow.player_name || 'Unknown pitcher';
  const pitch = topRow.pitch_name || topRow.pitch_type || 'Pitch';

  return `
    <article class="leaderboard-profile-card card p-4">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs uppercase tracking-[0.12em] text-zinc-500">#${rank} ${isPitcher ? 'Pitcher' : 'Hitter'}</p>
          <a class="block truncate text-2xl font-semibold leading-none hover:text-[var(--accent-soft)]" href="${profileUrl}">${escapeHtml(item.name)}</a>
        </div>
        <span class="text-3xl font-semibold text-[var(--accent-soft)]">${item.count}</span>
      </div>
      <div class="leaderboard-profile-stats">
        <div>
          <p>Avg</p>
          <strong>${item.avgScore.toFixed(1)}</strong>
        </div>
        <div>
          <p>${isPitcher ? 'Best' : 'Worst'}</p>
          <strong>${item.bestScore.toFixed(1)}</strong>
        </div>
        <div>
          <p>Swords</p>
          <strong>${item.count}</strong>
        </div>
      </div>
      <p class="mt-3 text-sm text-zinc-400">
        Top sword: ${escapeHtml(pitch)} on ${formatDate(topRow.game_date)}
        ${isPitcher ? 'vs' : 'from'} ${escapeHtml(opponent)}.
      </p>
      <div class="leaderboard-card-actions">
        <a class="primary rounded-md px-3 py-2 text-xs uppercase tracking-[0.08em]" href="${topSwordUrl}">View Top Sword</a>
        <a class="secondary rounded-md px-3 py-2 text-xs uppercase tracking-[0.08em]" href="${profileUrl}">${isPitcher ? 'Pitcher Profile' : 'Hitter History'}</a>
      </div>
    </article>
  `;
}

function renderHitterLeaderboardCards(rows) {
  const hitters = aggregateBy(rows, 'batter', 'batter_name')
    .sort((a, b) => b.count - a.count || b.bestScore - a.bestScore || b.avgScore - a.avgScore)
    .slice(0, 12);

  cardsRoot.className = 'leaderboard-profile-grid';
  cardsRoot.innerHTML = hitters.map((item, index) => renderProfileLeaderboardCard(item, index + 1, 'hitter')).join('');
  return hitters.length;
}

function renderPitcherLeaderboardCards(rows) {
  const pitchers = aggregateBy(rows, 'pitcher', 'pitcher_name')
    .sort((a, b) => b.count - a.count || b.bestScore - a.bestScore || b.avgScore - a.avgScore)
    .slice(0, 12);

  cardsRoot.className = 'leaderboard-profile-grid';
  cardsRoot.innerHTML = pitchers.map((item, index) => renderProfileLeaderboardCard(item, index + 1, 'pitcher')).join('');
  return pitchers.length;
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
  const selectedPitchType = activePitchType();
  if (selectedPitchType && !pitchTypeLabels.has(selectedPitchType)) {
    optionCodes.unshift(selectedPitchType);
  }

  pitchTypeFilter.innerHTML = [
    '<option value="">All pitch types</option>',
    '<optgroup label="Pitch families">',
    ...PITCH_FAMILIES.map(
      (family) => `<option value="family:${escapeHtml(family.id)}">${escapeHtml(family.label)}</option>`
    ),
    '</optgroup>',
    '<optgroup label="Individual pitch types">',
    ...optionCodes.map(
      (code) => `<option value="pitch:${escapeHtml(code)}">${escapeHtml(pitchTypeLabel(code))}</option>`
    ),
    '</optgroup>',
  ].join('');
  pitchTypeFilter.value = activePitchFilter;
  renderPitchTypeChips();
}

async function fetchLeaderboardRows(start) {
  const pageSize = 1000;
  const rows = [];
  const pitchType = activePitchType();

  for (let offset = 0; offset < 10000; offset += pageSize) {
    const params = {
      select: 'id,batter,pitcher,player_name,pitcher_name,batter_name,sword_score,game_date,pitch_type,pitch_name,release_speed,video_azure_blob_url',
      game_type: 'eq.R',
      sword_score: 'gte.90',
      game_date: [`gte.${start}`, `lte.${latestDate}`],
      order: 'sword_score.desc',
      limit: pageSize,
      offset,
    };
    if (pitchType) {
      params.pitch_type = `eq.${pitchType}`;
    }

    const page = await fetchRows('mlb_pitches_enhanced', params);
    rows.push(...page);
    if (page.length < pageSize) break;
  }

  const family = activePitchFamily();
  if (!family) return rows;
  const allowedCodes = new Set(family.codes);
  return rows.filter((row) => allowedCodes.has(normalizePitchType(row.pitch_type)));
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
  const rows = await fetchLeaderboardRows(start);
  let displayedRows = 0;
  renderHitterTable(rows);
  renderPitcherTable(rows);

  const rangeLabel = activeRange === 'season' ? `${season.year} season` : `last ${activeRange === 'week' ? '7' : '30'} days`;
  const pitchLabel = activePitchLabel();

  if (activeBoardView === 'hitters') {
    displayedRows = renderHitterLeaderboardCards(rows);
    heading.textContent = 'Top Hitter Sword Leaders';
  } else if (activeBoardView === 'pitchers') {
    displayedRows = renderPitcherLeaderboardCards(rows);
    heading.textContent = 'Top Pitcher Sword Leaders';
  } else {
    displayedRows = renderTopSwordCards(rows);
    heading.textContent = activePitchType()
      ? `Top 5 ${activePitchType()} Swords`
      : `Top 5 By Pitch Type`;
  }

  if (!displayedRows) {
    setStatusText(`No ${pitchLabel} found for ${rangeLabel}.`);
    return;
  }

  if (activeBoardView === 'hitters') {
    setStatusText(`Showing ${displayedRows} hitter sword leaders for ${pitchLabel} in ${rangeLabel} ending ${formatDate(latestDate)}.`);
  } else if (activeBoardView === 'pitchers') {
    setStatusText(`Showing ${displayedRows} pitcher sword leaders for ${pitchLabel} in ${rangeLabel} ending ${formatDate(latestDate)}.`);
  } else {
    setStatusText(`Showing top 5 swords for ${pitchLabel} by pitch type for ${rangeLabel} ending ${formatDate(latestDate)}.`);
  }
}

rangeButtons.forEach((btn) => {
  btn.addEventListener('click', async () => {
    setActiveRange(btn.dataset.range);
    updateUrlState();
    await refresh();
  });
});

pitchTypeFilter.addEventListener('change', async () => {
  setActivePitchFilter(pitchTypeFilter.value);
  if (activePitchFilter) setActiveRange('season');
  updateUrlState();
  await refresh();
});

clearPitchFilterButton.addEventListener('click', async () => {
  setActivePitchFilter('');
  updateUrlState();
  await refresh();
});

bindPitchExplorer();
bindBoardViewTabs();
bindLeaderboardCardClicks();

async function init() {
  try {
    setStatusText('Loading leaderboard data');
    const params = new URLSearchParams(window.location.search);
    setActiveRange(params.get('range') || activeRange);
    setActiveBoardView(params.get('view'));
    if (activeBoardView !== 'pitch-types' && !params.has('range')) {
      setActiveRange('season');
    }
    const pitchType = normalizePitchType(params.get('pitch_type') || params.get('pitch'));
    const pitchGroup = String(params.get('pitch_group') || '').trim().toLowerCase();
    if (pitchType) {
      activePitchFilter = `pitch:${pitchType}`;
    } else if (PITCH_FAMILY_BY_ID.has(pitchGroup)) {
      activePitchFilter = `family:${pitchGroup}`;
    }
    updateUrlState();
    await fetchLatestDate();
    await fetchPitchTypeOptions();
    await refresh();
  } catch (error) {
    console.error(error);
    setStatusText(`Leaderboard load failed: ${error.message}`);
  }
}

init();
