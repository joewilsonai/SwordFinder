import {
  bindVideoHover,
  escapeHtml,
  fetchApiJson,
  formatDate,
  latestSeasonRange,
  linkForPitcher,
  parseEntityIdFromPath,
} from './supabase-rest.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav();
setFooter();

const season = latestSeasonRange();
const playerId = parseEntityIdFromPath('player');

const title = document.getElementById('profile-title');
const subtitle = document.getElementById('profile-subtitle');
const metricSwords = document.getElementById('metric-swords');
const metricAvg = document.getElementById('metric-avg');
const metricWorst = document.getElementById('metric-worst');
const metricRate = document.getElementById('metric-rate');
const historyRoot = document.getElementById('history-list');

function renderHistory(rows) {
  historyRoot.innerHTML = rows
    .map(
      (row, idx) => `
      <article class="card sword-card p-3 md:p-4" style="animation-delay:${idx * 70}ms">
        <div class="mb-2 flex items-center justify-between gap-4">
          <p class="text-sm text-zinc-400">${formatDate(row.game_date)} • ${escapeHtml(row.home_team || '')} vs ${escapeHtml(row.away_team || '')}</p>
          <span class="text-lg text-[var(--accent-soft)]">${Number(row.sword_score || 0).toFixed(1)}</span>
        </div>
        <p class="mb-2 text-sm text-zinc-200">
          vs <a class="underline decoration-zinc-600 hover:decoration-[var(--accent-soft)]" href="${linkForPitcher(row)}">${escapeHtml(row.pitcher_name || row.source_player_name || 'Unknown')}</a>
          • ${escapeHtml(row.pitch_type || '--')} ${Number(row.release_speed || 0).toFixed(1)} mph
        </p>
        <div class="video-shell">
          ${row.video_azure_blob_url ? `
            <video data-hover-unmute="true" autoplay muted loop playsinline controls preload="metadata">
              <source src="${row.video_azure_blob_url}" type="video/mp4" />
            </video>
          ` : `<div class="flex h-[220px] items-center justify-center text-sm text-zinc-500">Video pending</div>`}
        </div>
      </article>
    `
    )
    .join('');

  bindVideoHover(historyRoot);
}

async function init() {
  if (!playerId) {
    setStatusText('Player id is missing. Use /player/{id}.');
    return;
  }

  try {
    setStatusText(`Loading hitter profile ${playerId}`);

    const profile = await fetchApiJson(`/profiles/batter/${playerId}/swords`, {
      start_date: season.startDate,
      end_date: season.endDate,
      limit: 80,
      ensure_videos: 'true',
    });
    const rows = profile.rows || [];
    const totalPitches = Number(profile.total_pitches || 0);

    if (!rows.length) {
      title.textContent = `Hitter #${playerId}`;
      subtitle.textContent = `No sword events logged in ${season.year}.`;
      historyRoot.innerHTML = '<p class="text-zinc-400">No sword history found.</p>';
      setStatusText('No sword rows for this hitter id.');
      return;
    }

    const name = rows[0].batter_name || `Hitter #${playerId}`;
    const avg = rows.reduce((sum, r) => sum + Number(r.sword_score || 0), 0) / rows.length;
    const worst = rows.reduce((acc, r) => Math.max(acc, Number(r.sword_score || 0)), 0);
    const rate = totalPitches ? (rows.length / totalPitches) * 100 : 0;
    const hydrated = Number(profile.hydrated || 0);
    const pending = Number(profile.pending_videos || 0);

    title.textContent = name;
    subtitle.textContent = `${season.year} sword history (${rows.length} events tracked)`;
    metricSwords.textContent = String(rows.length);
    metricAvg.textContent = avg.toFixed(1);
    metricWorst.textContent = worst.toFixed(1);
    metricRate.textContent = `${rate.toFixed(2)}%`;

    renderHistory(rows);
    if (profile.hydration_error) {
      setStatusText(`Loaded profile for ${name}. Video fetch warning: ${profile.hydration_error}`);
    } else if (hydrated > 0) {
      setStatusText(`Loaded profile for ${name}. Cached ${hydrated} missing clip${hydrated === 1 ? '' : 's'}.`);
    } else if (pending > 0) {
      setStatusText(`Loaded profile for ${name}. ${pending} clip${pending === 1 ? '' : 's'} still pending.`);
    } else {
      setStatusText(`Loaded profile for ${name}.`);
    }
  } catch (error) {
    console.error(error);
    setStatusText(`Failed to load player profile: ${error.message}`);
  }
}

init();
