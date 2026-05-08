import {
  bindVideoHover,
  escapeHtml,
  fetchApiJson,
  fetchRows,
  formatDate,
  latestSeasonRange,
  linkForPitcher,
  linkForPlayer,
} from './supabase-rest.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav('home');
setFooter();

const heroDate = document.getElementById('hero-date');
const cardsRoot = document.getElementById('sword-cards');
const emptyRoot = document.getElementById('empty-state');
const dateInput = document.getElementById('slate-date-input');
const selectedDateMetric = document.getElementById('metric-selected-date');
const topScoreMetric = document.getElementById('metric-top-score');
const biggestMissMetric = document.getElementById('metric-biggest-miss');
const clipsReadyMetric = document.getElementById('metric-clips-ready');

const season = latestSeasonRange();
let currentSlateDate = null;

function isCompleteDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''));
}

function numericValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

async function getLatestSwordDate() {
  const rows = await fetchRows('mlb_pitches_enhanced', {
    select: 'game_date',
    sword_score: 'gt.0',
    game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    order: 'game_date.desc',
    limit: 1,
  });

  return rows[0]?.game_date || null;
}

function cardTemplate(row, idx) {
  const playerLink = linkForPlayer(row);
  const pitcherLink = linkForPitcher(row);
  const video = row.video_azure_blob_url;
  const score = Number(row.sword_score || 0).toFixed(1);
  const videoBadge = video ? 'Video ready' : 'Video pending';

  return `
    <article class="sword-card card overflow-hidden p-3 md:p-4" style="animation-delay:${idx * 80}ms">
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
        • ${escapeHtml(row.pitch_name || row.pitch_type || 'Pitch')} ${row.release_speed ? Number(row.release_speed).toFixed(1) : '--'} mph
        • ${escapeHtml(row.description || row.events || 'swinging strike')}
      </p>
      <div class="video-shell mb-3">
        ${video ? `
          <video data-hover-unmute="true" autoplay muted loop playsinline controls preload="metadata">
            <source src="${video}" type="video/mp4" />
          </video>
        ` : `<div class="video-placeholder text-sm text-zinc-500">Video not yet available</div>`}
      </div>
      <div class="grid grid-cols-3 gap-2 text-sm">
        <div class="rounded-md bg-zinc-900/80 p-2">
          <p class="text-[11px] uppercase tracking-[0.08em] text-zinc-500">Bat Speed</p>
          <p class="text-lg">${row.bat_speed ? Number(row.bat_speed).toFixed(1) : '--'} <span class="text-xs text-zinc-400">mph</span></p>
        </div>
        <div class="rounded-md bg-zinc-900/80 p-2">
          <p class="text-[11px] uppercase tracking-[0.08em] text-zinc-500">Swing Length</p>
          <p class="text-lg">${row.swing_length ? Number(row.swing_length).toFixed(1) : '--'} <span class="text-xs text-zinc-400">ft</span></p>
        </div>
        <div class="rounded-md bg-zinc-900/80 p-2">
          <p class="text-[11px] uppercase tracking-[0.08em] text-zinc-500">Miss</p>
          <p class="text-lg">${row.strike_zone_distance_inches !== null && row.strike_zone_distance_inches !== undefined ? Number(row.strike_zone_distance_inches).toFixed(1) : '--'} <span class="text-xs text-zinc-400">in</span></p>
        </div>
      </div>
    </article>
  `;
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
  dateInput.disabled = true;
  setStatusText(`Loading top 5 swords for ${formatDate(date)}`);

  try {
    if (updateUrl) updateUrlDate(date);
    heroDate.textContent = `Selected slate: ${formatDate(date)}`;
    const slate = await loadTopCards(date);
    updateHeroMetricsFromSlate(slate, date);
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

async function init() {
  try {
    setStatusText('Loading live swords for 2026');
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
