// services.js — Service cards (LXC + Docker) with category filters, status badges, and uptime indicators
// ES module — exports renderServices(data) returning HTML and initServiceFilters() for interactivity
//
// Data shape (from /data/services.json):
// {
//   lxc:   [{ id, name, ip?, status, ram_used?, ram_total?, ram_pct?, disk_pct?, uptime? }]
//   docker:[{ name, status, uptime?, ports?[], category? }]
// }

import { statusBadge, storageBar } from './common.js';

// ── Constants ────────────────────────────────────────────────────────────────

const DOCKER_CATEGORIES = ['media', 'monitoring', 'infra', 'apps', 'dev'];

const CATEGORY_LABELS = {
  all:     'All',
  lxc:     '🖥 LXC',
  media:   '📺 Media',
  monitoring: '📊 Monitoring',
  infra:   '🔧 Infra',
  apps:    '📱 Apps',
  dev:     '💻 Dev',
  other:   '📦 Other'
};

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Escape HTML entities so service names don't break the DOM */
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Normalize Docker status strings so statusBadge() can match them.
 * "running (healthy)" → "running", "exited (1)" → "stopped", etc.
 */
function normStatus(raw) {
  if (!raw) return 'unknown';
  const s = raw.toLowerCase();
  if (s.includes('running')  || s.includes('up'))   return 'running';
  if (s.includes('healthy'))                          return 'healthy';
  if (s.includes('exited')   || s.includes('stopped')) return 'stopped';
  if (s.includes('error')    || s.includes('unhealthy')) return 'error';
  if (s.includes('paused'))                            return 'pending';
  return raw;
}

/** Format a display label for the Docker status (e.g. "running (healthy)" → "healthy") */
function statusLabel(raw) {
  if (!raw) return '?';
  if (raw.includes('healthy')) return 'healthy';
  if (raw.includes('running')) return 'running';
  return raw;
}

/**
 * Parse human-readable uptime (e.g. "32h", "1w", "1d 17h") into a sortable number of minutes.
 * Falls back to 0 for unparseable values so they sort last.
 */
function uptimeMinutes(uptime) {
  if (!uptime) return 0;
  const s = String(uptime).toLowerCase();
  let mins = 0;
  // weeks
  const w = s.match(/(\d+)\s*w/);
  if (w) mins += parseInt(w[1], 10) * 7 * 24 * 60;
  // days
  const d = s.match(/(\d+)\s*d/);
  if (d) mins += parseInt(d[1], 10) * 24 * 60;
  // hours
  const h = s.match(/(\d+)\s*h/);
  if (h) mins += parseInt(h[1], 10) * 60;
  // minutes
  const m = s.match(/(\d+)\s*m/);
  if (m) mins += parseInt(m[1], 10);
  return mins;
}

/**
 * Sort Docker services: running first (by uptime desc), then non-running.
 * Within each group keep category order consistent.
 */
function sortDocker(services) {
  const catRank = Object.fromEntries(DOCKER_CATEGORIES.map((c, i) => [c, i]));
  return [...services].sort((a, b) => {
    const aRun = normStatus(a.status) === 'running' ? 0 : 1;
    const bRun = normStatus(b.status) === 'running' ? 0 : 1;
    if (aRun !== bRun) return aRun - bRun;           // running first
    if (aRun === 0) {                                 // both running — uptime desc
      const uptimeDiff = uptimeMinutes(b.uptime) - uptimeMinutes(a.uptime);
      if (uptimeDiff !== 0) return uptimeDiff;
    }
    // category order then alphabetical
    const ca = catRank[a.category] ?? 99;
    const cb = catRank[b.category] ?? 99;
    if (ca !== cb) return ca - cb;
    return (a.name || '').localeCompare(b.name || '');
  });
}

// ── LXC Cards ────────────────────────────────────────────────────────────────

function renderLXCCard(lxc) {
  const ramBar  = lxc.ram_pct != null ? storageBar(lxc.ram_pct)  : '';
  const diskBar = lxc.disk_pct != null ? storageBar(lxc.disk_pct) : '';

  return `
    <div class="card service-card" data-category="lxc" data-status="${esc(normStatus(lxc.status))}">
      <div class="service-card-header">
        <span class="service-card-name">${esc(lxc.name)}</span>
        ${lxc.id != null ? `<span class="service-card-lxc-id">LXC ${esc(String(lxc.id))}</span>` : ''}
        <span class="service-card-status">${statusBadge(normStatus(lxc.status))}</span>
      </div>
      <div class="service-card-resources">
        ${lxc.ram_used ? `
        <div class="service-card-resource">
          <span class="resource-label">RAM ${esc(lxc.ram_used)}${lxc.ram_total ? ' / ' + esc(lxc.ram_total) : ''}</span>
          ${ramBar}
        </div>` : ''}
        ${lxc.disk_pct != null ? `
        <div class="service-card-resource">
          <span class="resource-label">Disk</span>
          ${diskBar}
          <span class="resource-pct">${lxc.disk_pct}%</span>
        </div>` : ''}
      </div>
      <div class="service-card-uptime">
        ${lxc.uptime ? `🕐 ${esc(lxc.uptime)}` : ''}
      </div>
    </div>`;
}

// ── Docker Cards ─────────────────────────────────────────────────────────────

function renderDockerCard(svc) {
  const cat = svc.category || 'other';
  const ports = svc.ports && svc.ports.length > 0
    ? `<div class="service-card-ports">${svc.ports.map(p => `<span class="port-tag">:${esc(p)}</span>`).join('')}</div>`
    : '';

  return `
    <div class="card service-card docker-card" data-category="${esc(cat)}" data-status="${esc(normStatus(svc.status))}">
      <div class="service-card-header">
        <span class="service-card-name">${esc(svc.name)}</span>
        <span class="service-card-status">${statusBadge(normStatus(svc.status))} <span class="service-card-status-label">${esc(statusLabel(svc.status))}</span></span>
      </div>
      <div class="service-card-uptime">
        ${svc.uptime ? `🕐 ${esc(svc.uptime)}` : ''}
      </div>
      ${ports}
    </div>`;
}

// ── Section Group ────────────────────────────────────────────────────────────

function renderDockerGroup(category, services, countBadge) {
  if (!services.length) return '';

  const label = CATEGORY_LABELS[category] || CATEGORY_LABELS.other;

  return `
    <div class="service-category" data-category="${esc(category)}">
      <h3 class="service-category-title">${label} <span class="service-category-count">${services.length}</span></h3>
      <div class="card-grid">
        ${services.map(renderDockerCard).join('\n')}
      </div>
    </div>`;
}

// ── Filter Tabs ──────────────────────────────────────────────────────────────

function renderFilterTabs(data) {
  // Build the list of tabs that actually have content
  const available = ['all'];

  if (data.lxc && data.lxc.length > 0) available.push('lxc');

  const dockerCats = new Set();
  if (data.docker) {
    data.docker.forEach(s => dockerCats.add(s.category || 'other'));
  }
  // Preserve category order for known categories, append unknowns
  DOCKER_CATEGORIES.forEach(c => { if (dockerCats.has(c)) available.push(c); });
  // Any category not in the ordered list (shouldn't happen with known data but defensive)
  dockerCats.forEach(c => { if (!DOCKER_CATEGORIES.includes(c) && c !== 'other') available.push(c); });

  const totalCount = (data.lxc ? data.lxc.length : 0) + (data.docker ? data.docker.length : 0);

  return `
    <div class="filter-tabs" id="service-filter-tabs">
      ${available.map((cat, i) => `
        <button class="filter-tab${i === 0 ? ' filter-tab-active' : ''}" data-filter="${esc(cat)}">
          ${CATEGORY_LABELS[cat] || cat}
        </button>`).join('\n')}
      <span class="filter-tab-total">${totalCount} services</span>
    </div>`;
}

// ── Public API ───────────────────────────────────────────────────────────────

/**
 * Render the complete services section HTML.
 * @param {Object} data — Parsed services.json (shape: { lxc: [...], docker: [...] })
 * @returns {string} HTML string for the entire services section
 */
export function renderServices(data) {
  if (!data) return '<div class="card section-placeholder">No service data available</div>';

  const lxc = data.lxc || [];
  const docker = data.docker || [];

  let html = '';

  // Filter tabs
  html += renderFilterTabs(data);

  // ── LXC Section ──
  if (lxc.length > 0) {
    html += `
    <div class="service-category" data-category="lxc">
      <h3 class="service-category-title">🖥 LXC Containers <span class="service-category-count">${lxc.length}</span></h3>
      <div class="card-grid">
        ${lxc.map(renderLXCCard).join('\n')}
      </div>
    </div>`;
  }

  // ── Docker by Category ──
  if (docker.length > 0) {
    // Group by category
    const groups = {};
    docker.forEach(s => {
      const cat = s.category || 'other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(s);
    });

    // Render in defined order
    DOCKER_CATEGORIES.forEach(cat => {
      if (groups[cat]) {
        html += renderDockerGroup(cat, sortDocker(groups[cat]));
        delete groups[cat];
      }
    });

    // Any remaining unknown categories
    Object.keys(groups).sort().forEach(cat => {
      html += renderDockerGroup(cat, sortDocker(groups[cat]));
    });
  }

  // ── Empty state ──
  if (lxc.length === 0 && docker.length === 0) {
    html += '<div class="card section-placeholder">No services found</div>';
  }

  return html;
}

/**
 * Attach click handlers to filter tabs (call after DOM insertion).
 * Toggles visibility of service-category sections and individual cards.
 */
export function initServiceFilters() {
  const tabs = document.querySelectorAll('#service-filter-tabs .filter-tab');
  if (!tabs.length) return;

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const filter = tab.dataset.filter;

      // Update active tab
      tabs.forEach(t => t.classList.remove('filter-tab-active'));
      tab.classList.add('filter-tab-active');

      // Show/hide category sections
      const sections = document.querySelectorAll('.service-category');
      sections.forEach(section => {
        if (filter === 'all') {
          section.style.display = '';
        } else {
          section.style.display = section.dataset.category === filter ? '' : 'none';
        }
      });

      // Also hide individual cards not in the selected category
      // (for cards that might not be wrapped in a section)
      const cards = document.querySelectorAll('.service-card');
      cards.forEach(card => {
        if (filter === 'all') {
          card.style.display = '';
        } else {
          card.style.display = card.dataset.category === filter ? '' : 'none';
        }
      });
    });
  });
}
