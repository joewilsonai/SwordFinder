import { mountFirstVisitIntro, mountNav, setFooter } from './layout.js';

mountNav('info');
setFooter();

async function copyCreatorPitch() {
  const pitch = document.getElementById('creator-pitch-text')?.textContent?.trim();
  const status = document.getElementById('creator-pitch-status');
  if (!pitch) return;

  try {
    await navigator.clipboard.writeText(pitch);
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = pitch;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
  }

  if (status) status.textContent = 'Pitch copied.';
}

document.getElementById('replay-intro')?.addEventListener('click', () => {
  try {
    window.localStorage.removeItem('swordfinder:intro:v3');
  } catch {
    // Storage can be unavailable in private or hardened browser contexts.
  }
  mountFirstVisitIntro({ force: true });
});

document.getElementById('copy-creator-pitch')?.addEventListener('click', copyCreatorPitch);
