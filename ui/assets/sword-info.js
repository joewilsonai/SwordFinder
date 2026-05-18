import { mountFirstVisitIntro, mountNav, setFooter } from './layout.js';

mountNav('info');
setFooter();

document.getElementById('replay-intro')?.addEventListener('click', () => {
  try {
    window.localStorage.removeItem('swordfinder:intro:v2');
  } catch {
    // Storage can be unavailable in private or hardened browser contexts.
  }
  mountFirstVisitIntro({ force: true });
});
