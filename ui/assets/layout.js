
const INTRO_STORAGE_KEY = 'swordfinder:intro:v3';
let introMounted = false;

const THEME_STORAGE_KEY = 'swordfinder:theme:v1';
const DEFAULT_THEME = 'red';
export const THEMES = [
  { id: 'red', label: 'Sword Red' },
  { id: 'blue', label: 'Diamond Blue' },
  { id: 'green', label: 'Outfield Green' },
  { id: 'gold', label: 'Bullpen Gold' },
  { id: 'purple', label: 'Midnight Purple' },
];

function isKnownTheme(id) {
  return THEMES.some((theme) => theme.id === id);
}

export function getStoredTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isKnownTheme(stored) ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function applyTheme(id) {
  const theme = isKnownTheme(id) ? id : DEFAULT_THEME;
  document.documentElement.setAttribute('data-theme', theme);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // If storage is blocked, the theme still applies for this page view.
  }
  return theme;
}

// Apply the saved theme as soon as this module evaluates so the palette is set
// before the nav (and the rest of the page) is mounted, avoiding a color flash.
applyTheme(getStoredTheme());

function hasSeenIntro() {
  try {
    return window.localStorage.getItem(INTRO_STORAGE_KEY) === 'seen';
  } catch {
    return false;
  }
}

function markIntroSeen() {
  try {
    window.localStorage.setItem(INTRO_STORAGE_KEY, 'seen');
  } catch {
    // If storage is blocked, the dismiss action should still work for this page view.
  }
}

function closeIntro(intro) {
  markIntroSeen();
  intro.classList.remove('is-visible');
  window.setTimeout(() => {
    intro.remove();
    introMounted = false;
  }, 180);
}

function shouldForceIntro() {
  return new URLSearchParams(window.location.search).get('intro') === '1';
}

export function mountFirstVisitIntro(options = {}) {
  const force = Boolean(options.force || shouldForceIntro());
  if (introMounted || (!force && hasSeenIntro())) return;

  const intro = document.createElement('div');
  intro.className = 'sword-intro';
  intro.setAttribute('role', 'dialog');
  intro.setAttribute('aria-modal', 'true');
  intro.setAttribute('aria-labelledby', 'sword-intro-title');
  intro.innerHTML = `
    <div class="sword-intro-panel">
      <button class="sword-intro-close" type="button" aria-label="Dismiss intro" data-sword-intro-dismiss>&times;</button>
      <p class="text-xs uppercase tracking-[0.14em] text-zinc-500">New here?</p>
      <h2 id="sword-intro-title" class="brand-title mt-2 text-4xl leading-none text-zinc-100">What's a Sword?</h2>
      <p class="mt-3 text-base leading-relaxed text-zinc-300">
        A sword is the swing a hitter makes when a pitch fools him so badly the bat stops out front like he's holding a sword.
      </p>
      <div class="sword-intro-notes mt-4">
        <p><span>1</span> Spot the shape: the hitter is fooled and the bat dies out front.</p>
        <p><span>2</span> Finish the at-bat: no K, no sword. A strikeout makes the ugly swing stick.</p>
        <p><span>3</span> Read the score: 90+ makes the board, 100+ is elite ugly.</p>
      </div>
      <div class="mt-5 flex flex-col gap-2 sm:flex-row">
        <button class="primary rounded-md px-4 py-2 text-sm uppercase tracking-[0.08em]" type="button" data-sword-intro-dismiss>Start Watching</button>
        <a class="secondary rounded-md px-4 py-2 text-sm uppercase tracking-[0.08em]" href="/sword-info.html" data-sword-intro-dismiss>Open Sword Info</a>
      </div>
      <a class="mt-3 inline-flex min-h-12 items-center text-sm text-zinc-400 underline decoration-zinc-700 hover:text-zinc-200 hover:decoration-[var(--accent-soft)]" href="/leaderboards.html" data-sword-intro-dismiss>Skip to leaderboards</a>
    </div>
  `;

  document.body.appendChild(intro);
  introMounted = true;

  const dismiss = () => closeIntro(intro);
  intro.querySelectorAll('[data-sword-intro-dismiss]').forEach((target) => {
    target.addEventListener('click', dismiss);
  });
  intro.addEventListener('click', (event) => {
    if (event.target === intro) dismiss();
  });
  intro.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') dismiss();
  });

  window.requestAnimationFrame(() => intro.classList.add('is-visible'));
  intro.querySelector('[data-sword-intro-dismiss]')?.focus();
}

export function mountNav(active = 'home') {
  // The Feedback launcher is shared chrome: mount it on every page that renders
  // the nav, before any early return so it is always available.

  const nav = document.getElementById('top-nav');
  if (!nav) return;

  nav.innerHTML = `
    <div class="app-nav-shell mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 md:px-6">
      <a href="/index.html" class="flex items-center gap-2 app-brand" aria-label="SwordFinder home">
        <img class="brand-mark" src="/assets/brand/swordfinder-mark-white.png" alt="" />
        <span class="brand-title text-3xl tracking-[0.14em]">SwordFinder</span>
      </a>
      <div class="app-nav flex items-center gap-2 text-sm uppercase tracking-[0.09em] md:gap-6">
        <a class="app-link ${active === 'home' ? 'active' : ''}" href="/index.html">Home</a>
        <a class="app-link ${active === 'info' ? 'active' : ''}" href="/sword-info.html">Info</a>
        <a class="app-link ${active === 'leaderboards' ? 'active' : ''}" href="/leaderboards.html"><span class="nav-label-full">Leaderboards</span><span class="nav-label-short">Boards</span></a>
        <a class="app-link ${active === 'ops' ? 'active' : ''}" href="/ops.html">Ops</a>
        <label class="theme-picker">
          <span class="sr-only">Color theme</span>
          <select id="theme-select" class="theme-select" aria-label="Color theme">
            ${THEMES.map((theme) => `<option value="${theme.id}">${theme.label}</option>`).join('')}
          </select>
        </label>
      </div>
    </div>
  `;

  const themeSelect = nav.querySelector('#theme-select');
  if (themeSelect) {
    themeSelect.value = getStoredTheme();
    themeSelect.addEventListener('change', (event) => {
      applyTheme(event.target.value);
    });
  }

  if (active !== 'ops') {
    mountFirstVisitIntro();
  }
}

export function setFooter() {
  const footer = document.getElementById('app-footer');
  if (!footer) return;

  footer.innerHTML = `
    <div class="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-6 text-xs text-zinc-400 md:flex-row md:items-center md:justify-between md:px-6">
      <p>Questions or a sword we missed? <a class="underline" href="https://github.com/joewilsonai/SwordFinder/issues">Open an issue</a>.</p>
      <p>Data from Statcast via Baseball Savant, rebuilt daily. Not affiliated with MLB.</p>
    </div>
  `;
}

export function setStatusText(message) {
  const target = document.getElementById('status-text');
  if (target) {
    target.textContent = message;
  }
}
