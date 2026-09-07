// Quick reference module — collapsible accordion sections
// Imports helpers from common.js

import { timeAgo, statusBadge, copyToClipboard } from './common.js';

/**
 * Render the quick-reference accordion from reference.json data.
 * @param {Object} data — reference.json payload
 * @returns {string} HTML string
 */
export function renderReference(data) {
  if (!data) return '<div class="accordion">No reference data available</div>';

  const sections = [];

  // 1. Paths — key-value rows
  if (data.paths && data.paths.length) {
    sections.push(accordionPanel(
      'paths',
      '📁 Common Paths',
      renderPaths(data.paths)
    ));
  }

  // 2. Ports — table
  if (data.ports && data.ports.length) {
    sections.push(accordionPanel(
      'ports',
      '🔌 Service Ports',
      renderPorts(data.ports)
    ));
  }

  // 3. Common Commands — copy buttons
  if (data.common_commands && data.common_commands.length) {
    sections.push(accordionPanel(
      'commands',
      '💻 Common Commands',
      renderCommands(data.common_commands)
    ));
  }

  // 4. API Keys — masked values
  if (data.api_keys && data.api_keys.length) {
    sections.push(accordionPanel(
      'api_keys',
      '🔑 API Keys',
      renderApiKeys(data.api_keys)
    ));
  }

  // Inject inline accordion behaviour (IIFE on load — idempotent)
  const accordionScript = `
    <script>
      (function() {
        var headers = document.querySelectorAll('.accordion-header');
        for (var i = 0; i < headers.length; i++) {
          headers[i].addEventListener('click', function() {
            var panel = this.parentElement;
            var body = panel.querySelector('.accordion-body');
            var wasOpen = panel.classList.contains('open');
            // Close all
            var all = document.querySelectorAll('.accordion-panel');
            for (var j = 0; j < all.length; j++) all[j].classList.remove('open');
            // Toggle clicked (re-open if it was closed)
            if (!wasOpen) {
              panel.classList.add('open');
            }
          });
        }
      })();
    </script>`;

  return `<div class="accordion">${sections.join('')}</div>${accordionScript}`;
}

/* ── Section renderers ── */

function renderPaths(paths) {
  const rows = paths.map(p => `
    <div class="ref-row">
      <span class="ref-key">${esc(p.key)}</span>
      <code class="ref-value">${esc(p.value)}</code>
    </div>`);
  return `<div class="accordion-body-content">${rows.join('')}</div>`;
}

function renderPorts(ports) {
  const rows = ports.map(p => `
    <tr>
      <td>${esc(p.service)}</td>
      <td><code>${esc(String(p.port))}</code></td>
      <td class="ref-note">${p.note ? esc(p.note) : '—'}</td>
    </tr>`);
  return `
    <div class="accordion-body-content">
      <table class="ref-table">
        <thead><tr><th>Service</th><th>Port</th><th>Note</th></tr></thead>
        <tbody>${rows.join('')}</tbody>
      </table>
    </div>`;
}

function renderCommands(commands) {
  const blocks = commands.map(c => {
    const id = 'cmd-' + Math.random().toString(36).slice(2, 8);
    return `
      <div class="cmd-row">
        <div class="cmd-label">${esc(c.action)}</div>
        <div class="cmd-block" id="${id}">
          <code>${esc(c.cmd)}</code>
          <button class="copy-btn" onclick="navigator.clipboard.writeText('${escAttr(c.cmd)}').then(function(){var b=document.getElementById('${id}').querySelector('.copy-btn');b.textContent='✓ Copied!';setTimeout(function(){b.textContent='📋 Copy';},2000)})">📋 Copy</button>
        </div>
      </div>`;
  });
  return `<div class="accordion-body-content">${blocks.join('')}</div>`;
}

function renderApiKeys(keys) {
  const rows = keys.map(k => `
    <div class="ref-row">
      <span class="ref-key">${esc(k.service)}</span>
      <span class="ref-value masked">${k.note ? '••••' + esc(k.note) : '••••••••'}</span>
      <span class="ref-note">${esc(k.key_ref || '')}</span>
    </div>`);
  return `<div class="accordion-body-content">${rows.join('')}</div>`;
}

/* ── Accordion panel builder ── */

let _panelIdx = 0;

function accordionPanel(id, label, bodyHtml) {
  _panelIdx++;
  const openClass = _panelIdx === 1 ? ' open' : ''; // first panel open by default
  return `
    <div class="accordion-panel${openClass}" data-section="${escAttr(id)}">
      <div class="accordion-header">
        <span class="accordion-arrow">▶</span>
        <span>${label}</span>
      </div>
      <div class="accordion-body">${bodyHtml}</div>
    </div>`;
}

/* ── Escape helpers ── */

function esc(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function escAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
