// Common helpers shared across all modules
// No framework dependencies — vanilla JS

const DATA_DIR = '/data/';
const REFRESH_INTERVAL = 60000; // 60 seconds

// Fetch JSON and cache
const _cache = {};
async function fetchJSON(filename) {
  if (_cache[filename] && Date.now() - _cache[filename].ts < REFRESH_INTERVAL) {
    return _cache[filename].data;
  }
  try {
    const resp = await fetch(DATA_DIR + filename);
    const data = await resp.json();
    _cache[filename] = { data, ts: Date.now() };
    return data;
  } catch (e) {
    console.warn(`Failed to fetch ${filename}:`, e);
    return null;
  }
}

// Format relative time
function timeAgo(isoString) {
  if (!isoString) return 'unknown';
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// Status badge
function statusBadge(status) {
  const map = {
    'running': '<span class="badge badge-ok">✅</span>',
    'ok': '<span class="badge badge-ok">✅</span>',
    'healthy': '<span class="badge badge-ok">✅ healthy</span>',
    'warning': '<span class="badge badge-warn">⚠️</span>',
    'error': '<span class="badge badge-err">🔴</span>',
    'pending': '<span class="badge badge-info">⏳</span>',
    'stopped': '<span class="badge badge-err">⛔</span>',
  };
  return map[status] || `<span class="badge">${status}</span>`;
}

// Severity colors
function severityClass(severity) {
  return { error: 'err', warning: 'warn', info: 'info' }[severity] || 'info';
}

// Priority colors
function priorityClass(priority) {
  return { high: 'err', medium: 'warn', low: 'info' }[priority] || 'info';
}

// Storage bar
function storageBar(pct) {
  const cls = pct > 90 ? 'err' : pct > 75 ? 'warn' : pct > 60 ? 'warn' : 'ok';
  return `<div class="storage-bar"><div class="storage-bar-fill storage-bar-${cls}" style="width:${Math.min(pct, 100)}%"></div></div>`;
}

// Copy to clipboard
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    const toast = document.getElementById('toast');
    toast.textContent = 'Copied!';
    toast.className = 'toast show';
    setTimeout(() => toast.className = 'toast', 2000);
  });
}

// Format number
function fmt(n, decimals = 1) {
  if (n == null) return '—';
  return Number(n).toFixed(decimals);
}

export { fetchJSON, timeAgo, statusBadge, severityClass, priorityClass, storageBar, copyToClipboard, fmt, DATA_DIR, REFRESH_INTERVAL };
