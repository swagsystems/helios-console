// Cron jobs module — renders cron job status cards
// Imports helpers from common.js

import { timeAgo, statusBadge } from './common.js';

/**
 * Render cron job status as a horizontal row of compact cards.
 * @param {Object} data — cron.json payload: { _meta: {...}, jobs: [...] }
 * @returns {string} HTML string
 */
export function renderCronJobs(data) {
  if (!data || !data.jobs || !data.jobs.length) {
    return '<div class="cron-row"><div class="cron-card"><span class="cron-name">No cron jobs configured</span></div></div>';
  }

  const cards = data.jobs.map(job => {
    const badge = statusBadge(job.last_status);
    const ago = timeAgo(job.last_run === '-' ? null : job.last_run);

    // Generate meta row with schedule + next run if available
    let scheduleInfo = job.schedule;
    if (job.next_run && job.next_run !== '-') {
      scheduleInfo += ` · next: ${timeAgo(job.next_run)}`;
    }

    return `
      <div class="cron-card">
        <div class="cron-name">${esc(job.name)}</div>
        <div class="cron-schedule">${esc(scheduleInfo)}</div>
        <div class="cron-meta">
          <span class="cron-status">${badge}</span>
          <span class="cron-lastrun">${esc(ago)}</span>
        </div>
      </div>`;
  });

  return `<div class="cron-row">${cards.join('')}</div>`;
}

// Minimal HTML escape (no external dep)
function esc(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}
