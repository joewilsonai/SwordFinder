import {
  bindVideoHover,
  escapeHtml,
  fetchCount,
  fetchRows,
  formatCompact,
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
const latestCount = document.getElementById('metric-latest-count');
const seasonCount = document.getElementById('metric-season-count');
const worstBatSpeed = document.getElementById('metric-worst-speed');
const totalVideos = document.getElementById('metric-video-count');

const season = latestSeasonRange();

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

  return `
    <article class="sword-card card overflow-hidden p-3 md:p-4" style="animation-delay:${idx * 80}ms">
      <div class="mb-2 flex items-center justify-between">
        <span class="badge bg-zinc-900/80">${formatDate(row.game_date)}</span>
        <span class="text-xl font-semibold text-[var(--accent-soft)]">${Number(row.sword_score || 0).toFixed(1)}</span>
      </div>
      <div class="mb-2 flex items-baseline justify-between gap-4">
        <a class="text-xl font-semibold hover:text-[var(--accent-soft)]" href="${playerLink}">${escapeHtml(row.player_name || 'Unknown hitter')}</a>
        <span class="text-xs uppercase tracking-[0.08em] text-zinc-400">${escapeHtml(row.home_team || '')} vs ${escapeHtml(row.away_team || '')}</span>
      </div>
      <p class="mb-3 text-sm text-zinc-300">
        vs <a class="underline decoration-zinc-500 hover:decoration-[var(--accent-soft)]" href="${pitcherLink}">${escapeHtml(row.pitcher_name || 'Unknown pitcher')}</a>
        • ${escapeHtml(row.pitch_type || row.pitch_name || 'Pitch')} ${Number(row.release_speed || 0).toFixed(1)} mph
      </p>
      <div class="video-shell mb-3">
        ${video ? `
          <video data-hover-unmute="true" autoplay muted loop playsinline controls preload="metadata">
            <source src="${video}" type="video/mp4" />
          </video>
        ` : `<div class="flex h-[230px] items-center justify-center text-sm text-zinc-500">Video not yet available</div>`}
      </div>
      <div class="grid grid-cols-3 gap-2 text-sm">
        <div class="rounded-md bg-zinc-900/80 p-2">
          <p class="text-[11px] uppercase tracking-[0.08em] text-zinc-500">Bat Speed</p>
          <p class="text-lg">${row.bat_speed ? Number(row.bat_speed).toFixed(1) : '--'} <span class="text-xs text-zinc-400">mph</span></p>
        </div>
        <div class="rounded-md bg-zinc-900/80 p-2">
          <p class="text-[11px] uppercase tracking-[0.08em] text-zinc-500">Swing Tilt</p>
          <p class="text-lg">${row.swing_path_tilt ? Number(row.swing_path_tilt).toFixed(1) : '--'}<span class="text-xs text-zinc-400">°</span></p>
        </div>
        <div class="rounded-md bg-zinc-900/80 p-2">
          <p class="text-[11px] uppercase tracking-[0.08em] text-zinc-500">Inning</p>
          <p class="text-lg">${row.inning || '--'}<span class="text-xs text-zinc-400"> ${row.inning_topbot || ''}</span></p>
        </div>
      </div>
    </article>
  `;
}

async function loadHeroMetrics(latestDate) {
  const [seasonSwordCount, seasonVideoCount, latestDayCount, worstSpeedRows] = await Promise.all([
    fetchCount('mlb_pitches_enhanced', {
      select: 'id',
      sword_score: 'gt.0',
      game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
    }),
    fetchCount('mlb_pitches_enhanced', {
      select: 'id',
      sword_score: 'gt.0',
      game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
      video_azure_blob_url: 'not.is.null',
    }),
    latestDate
      ? fetchCount('mlb_pitches_enhanced', {
          select: 'id',
          sword_score: 'gt.0',
          game_date: `eq.${latestDate}`,
        })
      : Promise.resolve(0),
    fetchRows('mlb_pitches_enhanced', {
      select: 'bat_speed',
      sword_score: 'gt.0',
      bat_speed: 'gt.0',
      game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
      order: 'bat_speed.asc',
      limit: 1,
    }),
  ]);

  seasonCount.textContent = formatCompact(seasonSwordCount);
  totalVideos.textContent = formatCompact(seasonVideoCount);
  latestCount.textContent = formatCompact(latestDayCount);
  worstBatSpeed.textContent = worstSpeedRows[0]?.bat_speed
    ? `${Number(worstSpeedRows[0].bat_speed).toFixed(1)} mph`
    : '--';
}

async function loadTopCards(latestDate) {
  if (!latestDate) {
    emptyRoot.classList.remove('hidden');
    cardsRoot.classList.add('hidden');
    setStatusText('No swords found for the configured season yet.');
    return;
  }

  const rows = await fetchRows('mlb_pitches_enhanced', {
    select:
      'id,batter,pitcher,player_name,pitcher_name,home_team,away_team,game_date,sword_score,bat_speed,swing_path_tilt,pitch_type,pitch_name,release_speed,video_azure_blob_url,inning,inning_topbot',
    game_date: `eq.${latestDate}`,
    sword_score: 'gt.0',
    order: 'sword_score.desc',
    limit: 12,
  });

  if (!rows.length) {
    emptyRoot.classList.remove('hidden');
    cardsRoot.classList.add('hidden');
    setStatusText(`No sword clips available for ${formatDate(latestDate)}.`);
    return;
  }

  cardsRoot.innerHTML = rows.map(cardTemplate).join('');
  cardsRoot.classList.remove('hidden');
  emptyRoot.classList.add('hidden');

  setStatusText(`Top sword swings from ${formatDate(latestDate)}.`);
  bindVideoHover(cardsRoot);
}

async function init() {
  try {
    setStatusText('Loading live swords for 2026');
    const latestDate = await getLatestSwordDate();

    heroDate.textContent = latestDate
      ? `Latest slate: ${formatDate(latestDate)}`
      : `Season ${season.year} has no swords yet`;

    await Promise.all([loadHeroMetrics(latestDate), loadTopCards(latestDate)]);
  } catch (error) {
    console.error(error);
    setStatusText('Could not load SwordFinder data right now.');
    emptyRoot.classList.remove('hidden');
    cardsRoot.classList.add('hidden');
    emptyRoot.innerHTML = `<p class="text-sm text-zinc-400">${escapeHtml(error.message)}</p>`;
  }
}

init();
