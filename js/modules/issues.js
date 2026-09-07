/**
 * Helios Dashboard — Known Issues Module
 *
 * Renders known issues / watchlist from issues.json.
 * Exports: renderIssues(data)
 *
 * Data shape: { issues: [{ id, severity, title, detail, action }] }
 *
 * Features:
 *   - Severity-colored left border (red=error, yellow=warning, blue=info)
 *   - Severity badge with icon
 *   - Detail text (full description)
 *   - Action text (recommended resolution)
 *   - Sorted by severity (error → warning → info)
 */

import { severityClass } from './common.js';

/* Severity → badge content mapping */
const SEVERITY_BADGE = {
  error:   '🔴 Error',
  warning: '🟡 Warning',
  info:    '🔵 Info',
};

/* Severity sort weight */
const SEVERITY_WEIGHT = { error: 0, warning: 1, info: 2 };

/**
 * Escapes HTML entities so JSON string content renders safely.
 * @param {string} str
 * @returns {string}
 */
const escapeHTML = (str) =>
  String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

/**
 * Render a single issue card.
 *
 * @param {object} issue — { id, severity, title, detail, action }
 * @returns {string} HTML string
 */
function renderIssueCard(issue) {
  const scls   = severityClass(issue.severity);   // 'err' | 'warn' | 'info'
  const badge  = SEVERITY_BADGE[issue.severity] || '⚪ Unknown';
  const title  = escapeHTML(issue.title);
  const detail = issue.detail ? `<p class="issue-detail">${escapeHTML(issue.detail)}</p>` : '';
  const action = issue.action
    ? `<p class="issue-action"><strong>Action:</strong> ${escapeHTML(issue.action)}</p>`
    : '';

  return `
    <div class="issue-card issue-severity-${scls}" data-id="${escapeHTML(issue.id)}">
      <div class="issue-header">
        <span class="issue-severity" data-severity="${issue.severity}">${badge}</span>
        <span class="issue-title">${title}</span>
      </div>
      ${detail}
      ${action}
    </div>`;
}

/**
 * Render the full Known Issues section.
 *
 * @param {object} data — Parsed issues.json shape
 * @param {Array}  data.issues — Array of issue objects
 * @returns {string} HTML string for the issues section
 */
export function renderIssues(data) {
  if (!data || !Array.isArray(data.issues) || data.issues.length === 0) {
    return '<div class="issues-container"><p class="empty-state">No known issues 🎉</p></div>';
  }

  /* Sort by severity: error → warning → info */
  const sorted = [...data.issues].sort(
    (a, b) => (SEVERITY_WEIGHT[a.severity] ?? 99) - (SEVERITY_WEIGHT[b.severity] ?? 99)
  );

  const cardsHTML = sorted.map(renderIssueCard).join('');

  return `<div class="issues-container">${cardsHTML}</div>`;
}
