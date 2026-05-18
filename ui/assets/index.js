import {
  bindVideoHover,
  escapeHtml,
  fetchApiJson,
  fetchRows,
  formatDate,
  getApiBaseUrl,
  latestSeasonRange,
  linkForPitcher,
  linkForPlayer,
  linkForSword,
} from './supabase-rest.js';
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
const draftXPostButton = document.getElementById('draft-x-post');
const xDraftPanel = document.getElementById('x-draft-panel');
const xDraftText = document.getElementById('x-draft-text');
const xDraftMeta = document.getElementById('x-draft-meta');
const xDraftStatus = document.getElementById('x-draft-status');
const connectXButton = document.getElementById('connect-x-account');
const postXNowButton = document.getElementById('post-x-now');
const postTopSwordVideoButton = document.getElementById('post-top-sword-video');
const xPinPanel = document.getElementById('x-pin-panel');
const xPinInput = document.getElementById('x-pin-input');
const verifyXPinButton = document.getElementById('verify-x-pin');
const copyXDraftButton = document.getElementById('copy-x-draft');
const openXDraftButton = document.getElementById('open-x-draft');
const xSharingEnabled = Boolean(
  draftXPostButton &&
  xDraftPanel &&
  xDraftText &&
  xDraftMeta &&
  xDraftStatus &&
  connectXButton &&
  postXNowButton &&
  postTopSwordVideoButton &&
  xPinPanel &&
  xPinInput &&
  verifyXPinButton &&
  copyXDraftButton &&
  openXDraftButton
);

const season = latestSeasonRange();
let currentSlateDate = null;
let currentXPageUrl = '';
let currentXShareText = '';
let isXConnected = false;
let xScreenName = '';
let xMediaUploadEnabled = true;
let canPostTopSwordDirectly = false;
let pendingXOAuthToken = '';

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
          <video data-hover-unmute="true" autoplay muted loop playsinline controls preload="metadata">
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

function buildEditableShareText(draft = '') {
  const trimmedDraft = draft.trim();
  if (!currentXPageUrl) return trimmedDraft;
  if (trimmedDraft.includes(currentXPageUrl)) return trimmedDraft;

  const separator = '\n\n';
  const remaining = 280 - separator.length - currentXPageUrl.length;
  const boundedDraft = remaining > 0 && trimmedDraft.length > remaining
    ? `${trimmedDraft.slice(0, Math.max(remaining - 3, 0)).trim()}...`
    : trimmedDraft;

  return `${boundedDraft}${separator}${currentXPageUrl}`.trim();
}

function setXDraftControls(draft = '', shareText = '') {
  if (!xSharingEnabled) return;

  currentXShareText = shareText || buildEditableShareText(draft);
  const hasDraft = Boolean(currentXShareText.trim());
  copyXDraftButton.disabled = !hasDraft;
  postXNowButton.disabled = !hasDraft || !isXConnected;
  postTopSwordVideoButton.disabled = !canPostTopSwordDirectly || !currentSlateDate;
  postTopSwordVideoButton.textContent = xMediaUploadEnabled ? 'Post #1 Video' : 'Post #1 Link';
  postTopSwordVideoButton.title = xMediaUploadEnabled
    ? 'Post the #1 sword with native X video.'
    : 'Post the #1 sword with a SwordFinder watch link.';
  openXDraftButton.href = hasDraft
    ? `https://x.com/intent/post?text=${encodeURIComponent(currentXShareText)}`
    : 'https://x.com/intent/post';
  openXDraftButton.classList.toggle('pointer-events-none', !hasDraft);
  openXDraftButton.classList.toggle('opacity-50', !hasDraft);
}

function resetXDraftPanel() {
  if (!xSharingEnabled) return;

  xDraftPanel.classList.add('hidden');
  xPinPanel.classList.add('hidden');
  xDraftText.value = '';
  xPinInput.value = '';
  currentXPageUrl = '';
  currentXShareText = '';
  pendingXOAuthToken = '';
  xMediaUploadEnabled = true;
  canPostTopSwordDirectly = false;
  xDraftMeta.textContent = 'Ready for selected slate';
  xDraftStatus.textContent = '';
  setXDraftControls('');
}

function renderXConnectionStatus() {
  if (!xSharingEnabled) return;

  connectXButton.textContent = isXConnected
    ? (xScreenName ? `@${xScreenName}` : 'OAuth2 Ready')
    : 'Connect X';
  connectXButton.disabled = isXConnected;
  postXNowButton.disabled = !isXConnected || !currentXShareText;
  postTopSwordVideoButton.disabled = !canPostTopSwordDirectly || !currentSlateDate;
  postTopSwordVideoButton.textContent = xMediaUploadEnabled ? 'Post #1 Video' : 'Post #1 Link';
  postTopSwordVideoButton.title = xMediaUploadEnabled
    ? 'Post the #1 sword with native X video.'
    : 'Post the #1 sword with a SwordFinder watch link.';
}

function updateXDraftMeta(meta = {}) {
  if (!xSharingEnabled) return;

  if (meta.page_url) currentXPageUrl = meta.page_url;
  const count = xDraftText.value.length;
  const limit = Number(meta.limit || xDraftText.maxLength || 280);
  const model = meta.model ? ` • ${meta.model}` : '';
  const shareText = meta.share_text || buildEditableShareText(xDraftText.value);
  xDraftMeta.textContent = `${count}/${limit} draft chars${model}`;
  setXDraftControls(xDraftText.value, shareText);
}

async function copyXDraft() {
  if (!xSharingEnabled) return;

  const shareText = currentXShareText || buildEditableShareText(xDraftText.value);
  if (!shareText) return;

  try {
    await navigator.clipboard.writeText(shareText);
  } catch (_) {
    xDraftText.focus();
    xDraftText.select();
    document.execCommand('copy');
  }

  xDraftStatus.textContent = 'Copied.';
}

async function refreshXConnectionStatus() {
  if (!xSharingEnabled) return null;

  try {
    const status = await fetchApiJson('/share/x/oauth/status');
    isXConnected = Boolean(status.connected);
    xScreenName = status.screen_name || '';
    xMediaUploadEnabled = status.media_upload_enabled !== false;
    canPostTopSwordDirectly = Boolean(
      status.connected &&
      !status.admin_required &&
      status.auth_mode !== 'oauth1_browser_session'
    );
    renderXConnectionStatus();
    return status;
  } catch (error) {
    console.warn('Could not check X connection', error);
    isXConnected = false;
    xScreenName = '';
    xMediaUploadEnabled = false;
    canPostTopSwordDirectly = false;
    renderXConnectionStatus();
    return null;
  }
}

async function connectXAccount() {
  if (!xSharingEnabled) return;

  const apiBaseUrl = getApiBaseUrl();
  if (!apiBaseUrl) {
    xDraftStatus.textContent = 'API base URL is required for X OAuth.';
    return;
  }

  const authWindow = window.open('', 'swordfinder-x-oauth');
  connectXButton.disabled = true;
  xDraftStatus.textContent = 'Opening X authorization...';

  try {
    const payload = await fetchApiJson('/share/x/oauth/start-pin');
    pendingXOAuthToken = payload.oauth_token || '';
    xPinPanel.classList.remove('hidden');
    xPinInput.value = '';

    if (authWindow) {
      authWindow.location.href = payload.authorize_url;
      xDraftStatus.textContent = 'Authorize SwordFinder in the X tab, then paste the PIN here.';
    } else {
      xDraftStatus.innerHTML = `Open <a class="underline decoration-zinc-500 hover:decoration-[var(--accent-soft)]" href="${escapeHtml(payload.authorize_url)}" target="_blank" rel="noreferrer">X authorization</a>, then paste the PIN here.`;
    }
    xPinInput.focus();
  } catch (error) {
    if (authWindow) authWindow.close();
    console.error(error);
    xDraftStatus.textContent = error.message;
  } finally {
    connectXButton.disabled = false;
  }
}

async function verifyXPin() {
  if (!xSharingEnabled) return;

  const pin = xPinInput.value.trim();
  if (!pendingXOAuthToken || !pin) {
    xDraftStatus.textContent = 'Paste the X authorization PIN first.';
    return;
  }

  verifyXPinButton.disabled = true;
  xDraftStatus.textContent = 'Verifying X PIN...';

  try {
    const payload = await fetchApiJson('/share/x/oauth/pin', {}, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ oauth_token: pendingXOAuthToken, pin }),
    });
    pendingXOAuthToken = '';
    xPinInput.value = '';
    xPinPanel.classList.add('hidden');
    isXConnected = true;
    xScreenName = payload.screen_name || '';
    renderXConnectionStatus();
    setXDraftControls(xDraftText.value, currentXShareText);
    xDraftStatus.textContent = `Connected${xScreenName ? ` as @${xScreenName}` : ''}.`;
  } catch (error) {
    console.error(error);
    xDraftStatus.textContent = error.message;
    await refreshXConnectionStatus();
  } finally {
    verifyXPinButton.disabled = false;
  }
}

async function postXNow() {
  if (!xSharingEnabled) return;

  const shareText = currentXShareText || buildEditableShareText(xDraftText.value);
  if (!shareText || postXNowButton.disabled) return;

  postXNowButton.disabled = true;
  xDraftStatus.textContent = 'Posting to X...';

  try {
    const payload = await fetchApiJson('/share/x/post', {}, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: currentSlateDate, text: shareText }),
    });

    const postUrl = payload.url || `https://x.com/${payload.screen_name || 'i'}/status/${payload.id}`;
    xDraftStatus.innerHTML = `Posted as @${escapeHtml(payload.screen_name || xScreenName || 'connected account')}: <a class="underline decoration-zinc-500 hover:decoration-[var(--accent-soft)]" href="${escapeHtml(postUrl)}" target="_blank" rel="noreferrer">view on X</a>`;
  } catch (error) {
    console.error(error);
    xDraftStatus.textContent = error.message;
    await refreshXConnectionStatus();
  } finally {
    setXDraftControls(xDraftText.value, currentXShareText);
  }
}

async function postTopSwordVideo() {
  if (!xSharingEnabled) return;

  if (!currentSlateDate || postTopSwordVideoButton.disabled) return;

  postTopSwordVideoButton.disabled = true;
  xDraftPanel.classList.remove('hidden');
  const postKind = xMediaUploadEnabled ? 'video' : 'link';
  xDraftStatus.textContent = `Posting #1 sword ${postKind} with stats...`;

  try {
    const payload = await fetchApiJson('/share/x/top-sword', {}, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: currentSlateDate }),
    });

    if (payload.text) {
      xDraftText.value = payload.text;
      updateXDraftMeta({ share_text: payload.text, limit: 280 });
    }
    const postUrl = payload.url || `https://x.com/${payload.screen_name || 'i'}/status/${payload.id}`;
    const postedKind = payload.post_mode || (payload.media ? 'video' : 'link');
    const postedPrefix = postedKind === 'link' ? 'Posted #1 link' : 'Posted #1 video';
    xDraftStatus.innerHTML = `${postedPrefix} as @${escapeHtml(payload.screen_name || xScreenName || 'connected account')}: <a class="underline decoration-zinc-500 hover:decoration-[var(--accent-soft)]" href="${escapeHtml(postUrl)}" target="_blank" rel="noreferrer">view on X</a>`;
  } catch (error) {
    console.error(error);
    xDraftStatus.textContent = error.message;
    await refreshXConnectionStatus();
  } finally {
    renderXConnectionStatus();
  }
}

async function draftXPost() {
  if (!xSharingEnabled) return;

  if (!currentSlateDate || draftXPostButton.disabled) return;

  draftXPostButton.disabled = true;
  xDraftPanel.classList.remove('hidden');
  xDraftText.value = '';
  xDraftStatus.textContent = `Drafting for ${formatDate(currentSlateDate)}`;
  xDraftMeta.textContent = 'Working';
  setXDraftControls('');

  try {
    const payload = await fetchApiJson('/share/x/draft', {}, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: currentSlateDate, limit: 5 }),
    });

    xDraftText.value = payload.draft || '';
    const shareText = payload.share_text || '';
    updateXDraftMeta({ ...payload, share_text: shareText });
    await refreshXConnectionStatus();
    xDraftStatus.textContent = isXConnected
      ? `Ready to post${xScreenName ? ` as @${xScreenName}` : ' with the configured X token'}.${xMediaUploadEnabled ? '' : ' Video posting needs media.write.'}`
      : 'Connect X to post directly, or use Post on X to open the composer.';
  } catch (error) {
    console.error(error);
    xDraftMeta.textContent = 'Draft unavailable';
    xDraftStatus.textContent = error.message;
  } finally {
    draftXPostButton.disabled = false;
  }
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
  resetXDraftPanel();
  dateInput.disabled = true;
  setStatusText(`Loading top 5 swords for ${formatDate(date)}`);

  try {
    if (updateUrl) updateUrlDate(date);
    heroDate.textContent = `Selected slate: ${formatDate(date)}`;
    const slate = await loadTopCards(date);
    updateHeroMetricsFromSlate(slate, date);
    renderSwordOfDayFeature(slate, date);
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
if (xSharingEnabled) {
  draftXPostButton.addEventListener('click', draftXPost);
  connectXButton.addEventListener('click', connectXAccount);
  postXNowButton.addEventListener('click', postXNow);
  postTopSwordVideoButton.addEventListener('click', postTopSwordVideo);
  verifyXPinButton.addEventListener('click', verifyXPin);
  copyXDraftButton.addEventListener('click', copyXDraft);
  xDraftText.addEventListener('input', () => updateXDraftMeta());
  xPinInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      verifyXPin();
    }
  });
}

async function init() {
  try {
    setStatusText('Loading live swords for 2026');
    if (xSharingEnabled) {
      await refreshXConnectionStatus();
    }
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
