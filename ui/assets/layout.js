export function mountNav(active = 'home') {
  const nav = document.getElementById('top-nav');
  if (!nav) return;

  nav.innerHTML = `
    <div class="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 md:px-6">
      <a href="/index.html" class="flex items-center gap-2 app-brand" aria-label="SwordFinder home">
        <img class="brand-mark" src="/assets/brand/swordfinder-mark-white.png" alt="" />
        <span class="brand-title text-3xl tracking-[0.14em]">SwordFinder</span>
      </a>
      <div class="flex items-center gap-4 text-sm uppercase tracking-[0.09em] md:gap-6">
        <a class="app-link ${active === 'home' ? 'active' : ''}" href="/index.html">Home</a>
        <a class="app-link ${active === 'leaderboards' ? 'active' : ''}" href="/leaderboards.html">Leaderboards</a>
        <a class="app-link ${active === 'ops' ? 'active' : ''}" href="/ops.html">Ops</a>
      </div>
    </div>
  `;
}

export function setFooter() {
  const footer = document.getElementById('app-footer');
  if (!footer) return;

  footer.innerHTML = `
    <div class="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-6 text-xs text-zinc-400 md:flex-row md:items-center md:justify-between md:px-6">
      <p>MLB swings and swords, revived for the 2026 season.</p>
      <p>Video clips served from Azure Blob. Data from Statcast + Supabase.</p>
    </div>
  `;
}

export function setStatusText(message) {
  const target = document.getElementById('status-text');
  if (target) {
    target.textContent = message;
  }
}
