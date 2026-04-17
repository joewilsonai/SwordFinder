import {
  bindVideoHover,
  escapeHtml,
  fetchCount,
  fetchRows,
  formatDate,
  latestSeasonRange,
  linkForPlayer,
  parseEntityIdFromPath,
} from './supabase-rest.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav();
setFooter();

const season = latestSeasonRange();
const pitcherId = parseEntityIdFromPath('pitcher');

const title = document.getElementById('profile-title');
const subtitle = document.getElementById('profile-subtitle');
const metricInduced = document.getElementById('metric-induced');
const metricAvg = document.getElementById('metric-avg');
const metricBest = document.getElementById('metric-best');
const metricRate = document.getElementById('metric-rate');
const historyRoot = document.getElementById('history-list');

function renderHistory(rows) {
  historyRoot.innerHTML = rows
    .slice(0, 80)
    .map(
      (row, idx) => `
      <article class="card sword-card p-3 md:p-4" style="animation-delay:${idx * 65}ms">
        <div class="mb-2 flex items-center justify-between gap-4">
          <p class="text-sm text-zinc-400">${formatDate(row.game_date)} • ${escapeHtml(row.pitch_type || '--')} ${Number(row.release_speed || 0).toFixed(1)} mph</p>
          <span class="text-lg text-[var(--accent-soft)]">${Number(row.sword_score || 0).toFixed(1)}</span>
        </div>
        <p class="mb-2 text-sm text-zinc-200">
          induced on <a class="underline decoration-zinc-600 hover:decoration-[var(--accent-soft)]" href="${linkForPlayer(row)}">${escapeHtml(row.batter_name || 'Unknown')}</a>
          • bat speed ${row.bat_speed ? Number(row.bat_speed).toFixed(1) : '--'} mph
        </p>
        <div class="video-shell">
          ${row.video_azure_blob_url ? `
            <video data-hover-unmute="true" autoplay muted loop playsinline controls preload="metadata">
              <source src="${row.video_azure_blob_url}" type="video/mp4" />
            </video>
          ` : `<div class="flex h-[220px] items-center justify-center text-sm text-zinc-500">Video unavailable</div>`}
        </div>
      </article>
    `
    )
    .join('');

  bindVideoHover(historyRoot);
}

async function init() {
  if (!pitcherId) {
    setStatusText('Pitcher id is missing. Use /pitcher/{id}.');
    return;
  }

  try {
    setStatusText(`Loading pitcher profile ${pitcherId}`);

    const [rows, totalPitches] = await Promise.all([
      fetchRows('mlb_pitches_enhanced', {
        select:
          'id,pitcher,pitcher_name,batter,player_name,batter_name,game_date,pitch_type,release_speed,sword_score,bat_speed,video_azure_blob_url',
        pitcher: `eq.${pitcherId}`,
        sword_score: 'gt.0',
        game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
        order: 'sword_score.desc',
        limit: 140,
      }),
      fetchCount('mlb_pitches_enhanced', {
        select: 'id',
        pitcher: `eq.${pitcherId}`,
        game_date: [`gte.${season.startDate}`, `lt.${season.endDate}`],
      }),
    ]);

    if (!rows.length) {
      title.textContent = `Pitcher #${pitcherId}`;
      subtitle.textContent = `No induced swords logged in ${season.year}.`;
      historyRoot.innerHTML = '<p class="text-zinc-400">No induced swords found.</p>';
      setStatusText('No sword rows for this pitcher id.');
      return;
    }

    const name = rows[0].pitcher_name || rows[0].player_name || `Pitcher #${pitcherId}`;
    const avg = rows.reduce((sum, r) => sum + Number(r.sword_score || 0), 0) / rows.length;
    const best = rows.reduce((acc, r) => Math.max(acc, Number(r.sword_score || 0)), 0);
    const rate = totalPitches ? (rows.length / totalPitches) * 100 : 0;

    title.textContent = name;
    subtitle.textContent = `${season.year} sword inducer profile (${rows.length} events tracked)`;
    metricInduced.textContent = String(rows.length);
    metricAvg.textContent = avg.toFixed(1);
    metricBest.textContent = best.toFixed(1);
    metricRate.textContent = `${rate.toFixed(2)}%`;

    renderHistory(rows);
    setStatusText(`Loaded profile for ${name}.`);
  } catch (error) {
    console.error(error);
    setStatusText(`Failed to load pitcher profile: ${error.message}`);
  }
}

init();
