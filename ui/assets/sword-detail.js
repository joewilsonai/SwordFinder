import {
  bindVideoHover,
  escapeHtml,
  fetchRows,
  formatDate,
  linkForPitcher,
  linkForPlayer,
  parseEntityIdFromPath,
} from './supabase-rest.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav();
setFooter();

const swordId = parseEntityIdFromPath('sword');
const title = document.getElementById('sword-title');
const subtitle = document.getElementById('sword-subtitle');
const score = document.getElementById('sword-score');
const videoShell = document.querySelector('.sword-detail-video');
const videoPlaceholder = document.getElementById('sword-video-placeholder');
const scoreHeadline = document.getElementById('score-headline');
const scoreBreakdown = document.getElementById('score-breakdown');
const hitterLink = document.getElementById('hitter-link');
const pitcherLink = document.getElementById('pitcher-link');

function numericValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatDecimal(value, decimals = 1) {
  const number = numericValue(value);
  return number !== null ? number.toFixed(decimals) : '--';
}

function formatDescription(row) {
  const pitch = row.pitch_name || row.pitch_type || 'Pitch';
  const pitcher = row.pitcher_name || row.player_name || 'Unknown pitcher';
  return `${pitch} ${formatDecimal(row.release_speed)} mph from ${pitcher}`;
}

function breakdownItem(label, value, detail) {
  return `
    <div class="score-breakdown-item">
      <p>${escapeHtml(label)}</p>
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(detail)}</span>
    </div>
  `;
}

function renderVideo(row) {
  if (!row.video_azure_blob_url) {
    videoPlaceholder.textContent = 'Video pending';
    return;
  }

  videoShell.innerHTML = `
    <video data-hover-unmute="true" autoplay muted loop playsinline controls preload="metadata">
      <source src="${escapeHtml(row.video_azure_blob_url)}" type="video/mp4" />
    </video>
  `;
  bindVideoHover(videoShell);
}

function renderBreakdown(row) {
  const scoreValue = numericValue(row.sword_score);
  const batSpeed = numericValue(row.bat_speed);
  const miss = numericValue(row.strike_zone_distance_inches);
  const swingLength = numericValue(row.swing_length);
  const pitchSpeed = numericValue(row.release_speed);
  const headline = [];

  if (scoreValue !== null && scoreValue >= 100) headline.push('Elite miss');
  if (batSpeed !== null && batSpeed <= 40) headline.push('dead bat');
  if (miss !== null && miss >= 10) headline.push('big chase');

  scoreHeadline.textContent = headline.length ? headline.join(' • ') : 'Strikeout sword';
  scoreBreakdown.innerHTML = [
    breakdownItem('Finish', row.events || 'strikeout', 'Only strikeout swings make the board.'),
    breakdownItem('Bat Speed', `${formatDecimal(row.bat_speed)} mph`, batSpeed !== null && batSpeed <= 40 ? 'Dead-bat territory.' : 'Fooled swing speed.'),
    breakdownItem('Miss Distance', `${formatDecimal(row.strike_zone_distance_inches)} in`, miss !== null && miss >= 10 ? 'The barrel was nowhere near it.' : 'Enough miss to matter.'),
    breakdownItem('Swing Length', `${formatDecimal(row.swing_length)} ft`, swingLength !== null && swingLength < 7 ? 'Short, cut-off swing.' : 'Awkward path through the zone.'),
    breakdownItem('Pitch Speed', `${formatDecimal(pitchSpeed)} mph`, row.pitch_name || row.pitch_type || 'Pitch context.'),
  ].join('');
}

async function init() {
  if (!swordId) {
    setStatusText('Sword id is missing. Use /sword/{id}.');
    return;
  }

  try {
    const rows = await fetchRows('mlb_pitches_enhanced', {
      select: 'id,game_date,game_pk,batter,pitcher,batter_name,pitcher_name,player_name,pitch_type,pitch_name,release_speed,effective_speed,perceived_velocity,release_spin_rate,description,events,zone,bat_speed,swing_length,swing_path_tilt,strike_zone_distance_inches,sword_score,video_azure_blob_url',
      id: `eq.${swordId}`,
      limit: 1,
    });
    const row = rows[0];

    if (!row) {
      title.textContent = 'Sword not found';
      subtitle.textContent = `No row matched sword id ${swordId}.`;
      setStatusText('No sword row found.');
      return;
    }

    title.textContent = row.batter_name || 'Unknown hitter';
    subtitle.innerHTML = `
      ${formatDate(row.game_date)} • ${escapeHtml(formatDescription(row))}
      • ${escapeHtml(row.events || 'strikeout')}
    `;
    score.textContent = formatDecimal(row.sword_score);
    hitterLink.href = linkForPlayer(row);
    pitcherLink.href = linkForPitcher(row);

    renderVideo(row);
    renderBreakdown(row);
    document.title = `SwordFinder | ${row.batter_name || `Sword ${swordId}`}`;
    setStatusText(`Loaded sword ${swordId}.`);
  } catch (error) {
    console.error(error);
    title.textContent = 'Could not load sword';
    subtitle.textContent = error.message;
    setStatusText(`Failed to load sword detail: ${error.message}`);
  }
}

init();
