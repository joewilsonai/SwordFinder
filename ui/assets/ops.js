import { escapeHtml, formatDate, getStatus } from './data.js';
import { mountNav, setFooter, setStatusText } from './layout.js';

mountNav('ops');
setFooter();

const status = getStatus();
const root = document.getElementById('ops-facts');

if (!status) {
  setStatusText('Could not read the status file.');
} else {
  const checked = new Date(status.checked_at);
  const hours = (Date.now() - checked.getTime()) / 36e5;
  setStatusText(hours > 48
    ? `The daily job hasn't checked in for ${Math.round(hours)} hours.`
    : `The daily job last ran ${checked.toLocaleString()}.`);
  const facts = [
    ['Season', status.season],
    ['Latest games read', status.latest_date ? formatDate(status.latest_date) : 'None yet'],
    ['Swords', Number(status.swords || 0).toLocaleString()],
    ['With a clip', Number(status.with_clip || 0).toLocaleString()],
    ['Pitches read', Number(status.pitches || 0).toLocaleString()],
    ['Errors, last run', Number(status.errors || 0) + Number(status.clip_errors || 0)],
  ];
  root.innerHTML = facts.map(([label, value]) => `
    <div class="card p-5">
      <p class="text-xs uppercase tracking-[0.14em] text-zinc-400">${escapeHtml(label)}</p>
      <p class="mt-3 text-2xl font-semibold">${escapeHtml(String(value))}</p>
    </div>`).join('');
}
