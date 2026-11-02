import {
  bindVideoHover,
  escapeHtml,
  fetchApiJson,
  fetchRows,
  formatDate,
  latestSeasonRange,
  linkForPitcher,
  linkForPlayer,
  linkForSword,
} from './data.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav('home');
setFooter();

const heroDate = document.getElementById('hero-date');
const swordOfDayRoot = document.getElementById('sword-of-day');
const cardsRoot = document.getElementById('sword-cards');
const emptyRoot = document.getElementById('empty-state');
const dateInput = document.getElementById('slate-date-input');
const selectedDateMetric = document.getElementById('metric-selected-date');
const topScoreMetric = document.getElementById('metric-top-score');
const biggestMissMetric = document.getElementById('metric-biggest-miss');
const clipsReadyMetric = document.getElementById('metric-clips-ready');
const shareXButton = document.getElementById('draft-x-post');

const season = latestSeasonRange();
let currentSlateDate = null;
let currentTopSword = null;

function isCompleteDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''));
}

function numericValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatDecimal(value, decimals = 1) {
  const number = numericValue(value);
  return number !== null ? number.toFixed(decimals) : '--';
}

function formatInteger(value) {
  const number = numericValue(value);
  return number !== null ? Math.round(number).toLocaleString('en-US') : '--';
}

function metricTile(label, value, unit = '') {
  const safeValue = escapeHtml(value);
  const safeUnit = escapeHtml(unit);

  return `
    <div class="stat-tile">
      <p class="text-[11px] uppercase tracking-[0.08em] text-zinc-500">${escapeHtml(label)}</p>
      <p class="stat-value">${safeValue}${safeUnit ? ` <span class="text-xs text-zinc-400">${safeUnit}</span>` : ''}</p>
    </div>
  `;
}

function describeScore(row) {
  const score = numericValue(row.sword_score);
  const miss = numericValue(row.strike_zone_distance_inches);
  const batSpeed = numericValue(row.bat_speed);
  const parts = [];

  if (score !== null && score >= 100) {
    parts.push('elite SwordFinder score');
  } else if (score !== null) {
    parts.push('board-level SwordFinder score');
  }
  if (batSpeed !== null && batSpeed <= 40) {
    parts.push('dead-bat swing');
  }
  if (miss !== null && miss >= 10) {
    parts.push('big miss');
  }

  return parts.length ? parts.join(' • ') : 'strikeout sword candidate';
}

async function getLatestSwordDate() {
  const rows = await fetchRows('mlb_pitches_enhanced', {
    select: 'game_date',
    game_type: 'eq.R',
    sword_score: 'gte.90',
    game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    order: 'game_date.desc',
    limit: 1,
  });

  return rows[0]?.game_date || null;
}

function cardTemplate(row, idx) {
  const playerLink = linkForPlayer(row);
  const pitcherLink = linkForPitcher(row);
  const swordLink = linkForSword(row);
  const video = row.video_azure_blob_url;
  const score = Number(row.sword_score || 0).toFixed(1);
  const videoBadge = video ? 'Video ready' : 'Video pending';
  const pitchName = row.pitch_name || row.pitch_type || 'Pitch';

  return `
    <article id="sword-${idx + 1}" class="sword-card card overflow-hidden p-3 md:p-4" style="animation-delay:${idx * 80}ms">
      <div class="mb-3 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div class="flex items-center gap-3">
          <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border border-zinc-700 bg-black/60 text-xl font-semibold text-[var(--accent-soft)]">${idx + 1}</span>
          <div>
            <p class="text-xs uppercase tracking-[0.12em] text-zinc-500">Sword #${idx + 1}</p>
            <a class="text-2xl font-semibold leading-none hover:text-[var(--accent-soft)]" href="${playerLink}">${escapeHtml(row.batter_name || 'Unknown hitter')}</a>
          </div>
        </div>
        <div class="flex items-center gap-2 md:justify-end">
          <span class="badge bg-zinc-900/80">${escapeHtml(videoBadge)}</span>
          <span class="text-2xl font-semibold text-[var(--accent-soft)]">${score}</span>
        </div>
      </div>
      <p class="mb-3 text-sm text-zinc-300">
        vs <a class="underline decoration-zinc-500 hover:decoration-[var(--accent-soft)]" href="${pitcherLink}">${escapeHtml(row.pitcher_name || row.player_name || 'Unknown pitcher')}</a>
        • ${escapeHtml(pitchName)} ${formatDecimal(row.release_speed)} mph
        • ${escapeHtml(row.events || 'strikeout')}
      </p>
      <p class="mb-3 text-sm text-zinc-400">${escapeHtml(describeScore(row))}</p>
      <div class="video-shell mb-3">
        ${video ? `
          <video data-hover-unmute="true" data-play-on-screen="true" muted loop playsinline controls preload="none">
            <source src="${video}" type="video/mp4" />
          </video>
        ` : `<div class="video-placeholder text-sm text-zinc-500">Video not yet available</div>`}
      </div>
      <div class="mb-3">
        <p class="mb-2 text-xs uppercase tracking-[0.12em] text-zinc-500">Pitch Stats</p>
        <div class="pitch-stat-grid text-sm">
          ${metricTile('Pitch', pitchName)}
          ${metricTile('Pitch Speed', formatDecimal(row.release_speed), 'mph')}
          ${metricTile('Effective', formatDecimal(row.effective_speed), 'mph')}
          ${metricTile('Perceived', formatDecimal(row.perceived_velocity))}
          ${metricTile('Spin Rate', formatInteger(row.release_spin_rate), 'rpm')}
        </div>
      </div>
      <div class="grid grid-cols-3 gap-2 text-sm">
        ${metricTile('Bat Speed', formatDecimal(row.bat_speed), 'mph')}
        ${metricTile('Swing Length', formatDecimal(row.swing_length), 'ft')}
        ${metricTile('Miss', formatDecimal(row.strike_zone_distance_inches), 'in')}
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <a class="secondary rounded-md px-3 py-2 text-xs uppercase tracking-[0.08em]" href="${swordLink}">Open Sword Page</a>
        <a class="tap-target text-xs uppercase tracking-[0.08em] text-zinc-300 underline decoration-zinc-600 hover:decoration-[var(--accent-soft)]" href="${playerLink}">Hitter History</a>
      </div>
    </article>
  `;
}

function renderSwordOfDayFeature(slate, selectedDate) {
  if (!swordOfDayRoot) return;

  const row = slate?.rows?.[0];
  if (!row) {
    swordOfDayRoot.classList.add('hidden');
    swordOfDayRoot.innerHTML = '';
    return;
  }

  const pitchName = row.pitch_name || row.pitch_type || 'Pitch';
  const swordLink = linkForSword(row);
  const playerLink = linkForPlayer(row);
  const pitcherLink = linkForPitcher(row);

  swordOfDayRoot.innerHTML = `
    <div>
      <p class="text-xs uppercase tracking-[0.14em] text-zinc-500">Sword of the Day</p>
      <h2 class="brand-title mt-1 text-4xl leading-none text-zinc-100 md:text-5xl">${escapeHtml(row.batter_name || 'Unknown hitter')}</h2>
      <p class="mt-2 text-sm text-zinc-400">
        ${formatDate(selectedDate)} • vs <a class="underline decoration-zinc-600 hover:decoration-[var(--accent-soft)]" href="${pitcherLink}">${escapeHtml(row.pitcher_name || row.player_name || 'Unknown pitcher')}</a>
      </p>
    </div>
    <div class="daily-feature-stats">
      ${metricTile('Score', formatDecimal(row.sword_score))}
      ${metricTile('Pitch', pitchName)}
      ${metricTile('Bat Speed', formatDecimal(row.bat_speed), 'mph')}
      ${metricTile('Miss', formatDecimal(row.strike_zone_distance_inches), 'in')}
    </div>
    <div class="daily-feature-actions">
      <a class="primary rounded-md px-4 py-2 text-sm uppercase tracking-[0.08em]" href="${swordLink}">Open Sword Page</a>
      <a class="secondary rounded-md px-4 py-2 text-sm uppercase tracking-[0.08em]" href="${playerLink}">Hitter History</a>
    </div>
  `;
  swordOfDayRoot.classList.remove('hidden');
}

function updateHeroMetricsFromSlate(slate, selectedDate) {
  const rows = slate?.rows || [];
  const topScore = numericValue(rows[0]?.sword_score);
  const misses = rows
    .map((row) => numericValue(row.strike_zone_distance_inches))
    .filter((value) => value !== null);
  const biggestMiss = misses.length ? Math.max(...misses) : null;
  const readyClips = rows.filter((row) => row.video_azure_blob_url).length;

  selectedDateMetric.textContent = selectedDate ? formatDate(selectedDate) : '--';
  topScoreMetric.textContent = topScore !== null ? topScore.toFixed(1) : '--';
  biggestMissMetric.textContent = biggestMiss !== null ? `${biggestMiss.toFixed(1)} in` : '--';
  clipsReadyMetric.textContent = rows.length ? `${readyClips} / ${rows.length}` : '--';
}

function shareTopSword() {
  if (!currentTopSword) return;
  const row = currentTopSword;
  const hitter = row.batter_name || row.player_name || 'A hitter';
  const pitcher = row.pitcher_name || 'the pitcher';
  const text = `${hitter} got fooled by ${pitcher} on ${formatDate(row.game_date)}. Sword Score ${Math.round(row.sword_score)}.`;
  const url = new URL(linkForSword(row), window.location.origin).toString();
  const intent = `https://x.com/intent/post?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
  window.open(intent, '_blank', 'noopener');
}

async function loadTopCards(selectedDate) {
  if (!selectedDate) {
    emptyRoot.classList.remove('hidden');
    cardsRoot.classList.add('hidden');
    setStatusText('No swords found for the configured season yet.');
    return;
  }

  const slate = await fetchApiJson('/daily-slate', {
    date: selectedDate,
    limit: 5,
    ensure_videos: 'true',
  });
  const rows = slate.rows || [];

  if (!rows.length) {
    emptyRoot.classList.remove('hidden');
    cardsRoot.classList.add('hidden');
    setStatusText(`No swords found for ${formatDate(selectedDate)}.`);
    return slate;
  }

  cardsRoot.innerHTML = rows.map(cardTemplate).join('');
  cardsRoot.classList.remove('hidden');
  emptyRoot.classList.add('hidden');

  const hydrated = Number(slate.hydrated || 0);
  const pending = Number(slate.pending_videos || 0);
  let status = `Top 5 sword swings from ${formatDate(selectedDate)}.`;
  if (hydrated > 0) {
    status += ` Cached ${hydrated} missing ${hydrated === 1 ? 'video' : 'videos'}.`;
  }
  if (pending > 0) {
    status += ` ${pending} ${pending === 1 ? 'clip is' : 'clips are'} still pending.`;
  }
  setStatusText(status);
  bindVideoHover(cardsRoot);
  return slate;
}

function updateUrlDate(date) {
  const url = new URL(window.location.href);
  url.searchParams.set('date', date);
  window.history.replaceState({}, '', url);
}

async function refreshSlate(date, options = {}) {
  const { updateUrl = true } = options;
  if (!isCompleteDate(date)) return;

  currentSlateDate = date;
  currentTopSword = null;
  dateInput.disabled = true;
  setStatusText(`Loading top 5 swords for ${formatDate(date)}`);

  try {
    if (updateUrl) updateUrlDate(date);
    heroDate.textContent = `Selected slate: ${formatDate(date)}`;
    const slate = await loadTopCards(date);
    updateHeroMetricsFromSlate(slate, date);
    renderSwordOfDayFeature(slate, date);
    currentTopSword = slate?.rows?.[0] || null;
    if (shareXButton) shareXButton.disabled = !currentTopSword;
  } finally {
    dateInput.disabled = false;
  }
}

function refreshSelectedDate() {
  if (isCompleteDate(dateInput.value) && dateInput.value !== currentSlateDate) {
    refreshSlate(dateInput.value);
  }
}

dateInput.addEventListener('input', refreshSelectedDate);
dateInput.addEventListener('change', refreshSelectedDate);
if (shareXButton) shareXButton.addEventListener('click', shareTopSword);

async function init() {
  try {
    setStatusText('Loading the latest swords');
    const latestDate = await getLatestSwordDate();
    const requestedDate = new URLSearchParams(window.location.search).get('date');
    const selectedDate = requestedDate || latestDate;

    if (latestDate) {
      dateInput.max = latestDate;
    }
    if (selectedDate) {
      dateInput.value = selectedDate;
    }

    heroDate.textContent = selectedDate
      ? `Selected slate: ${formatDate(selectedDate)}`
      : `Season ${season.year} has no swords yet`;

    await refreshSlate(selectedDate, { updateUrl: Boolean(requestedDate) });
  } catch (error) {
    console.error(error);
    setStatusText('Could not load SwordFinder data right now.');
    emptyRoot.classList.remove('hidden');
    cardsRoot.classList.add('hidden');
    emptyRoot.innerHTML = `<p class="text-sm text-zinc-400">${escapeHtml(error.message)}</p>`;
  }
}

init();
