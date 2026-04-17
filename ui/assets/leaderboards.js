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
const rangeButtons = Array.from(document.querySelectorAll('[data-range]'));

const season = latestSeasonRange();
let latestDate = null;
let activeRange = 'week';

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
      (row) => `
      <article class="card sword-card p-3 md:p-4">
        <div class="mb-2 flex items-center justify-between">
          <a class="font-semibold hover:text-[var(--accent-soft)]" href="${linkForPlayer(row)}">${escapeHtml(row.batter_name || 'Unknown')}</a>
          <span class="text-lg text-[var(--accent-soft)]">${Number(row.sword_score || 0).toFixed(1)}</span>
        </div>
        <p class="text-xs uppercase tracking-[0.08em] text-zinc-400">${formatDate(row.game_date)} • ${escapeHtml(row.pitch_type || '--')} ${Number(row.release_speed || 0).toFixed(1)} mph</p>
      </article>
    `
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
    sword_score: 'gt.0',
    game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    order: 'game_date.desc',
    limit: 1,
  });
  latestDate = rows[0]?.game_date || null;
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
  const rows = await fetchRows('mlb_pitches_enhanced', {
    select: 'id,batter,pitcher,player_name,pitcher_name,batter_name,sword_score,game_date,pitch_type,release_speed',
    sword_score: 'gt.0',
    game_date: [`gte.${start}`, `lte.${latestDate}`],
    order: 'sword_score.desc',
    limit: 500,
  });

  renderTopSwordCards(rows);
  renderHitterTable(rows);
  renderPitcherTable(rows);

  const label = activeRange === 'season' ? 'season' : activeRange;
  setStatusText(`Showing ${label} leaderboard ending ${formatDate(latestDate)}.`);
}

rangeButtons.forEach((btn) => {
  btn.addEventListener('click', async () => {
    rangeButtons.forEach((b) => b.classList.remove('primary'));
    rangeButtons.forEach((b) => b.classList.add('secondary'));
    btn.classList.remove('secondary');
    btn.classList.add('primary');
    activeRange = btn.dataset.range;
    await refresh();
  });
});

async function init() {
  try {
    setStatusText('Loading leaderboard data');
    await fetchLatestDate();
    await refresh();
  } catch (error) {
    console.error(error);
    setStatusText(`Leaderboard load failed: ${error.message}`);
  }
}

init();
