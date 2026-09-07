import { api } from "./api.js";
import { md } from "./markdown.js";

const COLLAPSE_KEY = "dash.tile.collapsed";
const loadCollapsed = () => {
  try { return new Set(JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "[]")); }
  catch { return new Set(); }
};
const saveCollapsed = (set) => {
  localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...set]));
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function safeUrl(url) {
  try {
    const u = new URL(url, window.location.origin);
    return ["http:", "https:"].includes(u.protocol) ? esc(u.href) : "#";
  } catch {
    return "#";
  }
}

export async function renderResources(el) {
  const items = await api.list("?type=note");
  const linkNotes = items.filter(i => (i.tags || []).includes("resource"));
  const pinnedNotes = items.filter(i => i.pinned);

  const links = linkNotes.flatMap(i => i.links || []);
  const linksHtml = links.length
    ? `<section class="res-links">${links.map(l =>
        `<a class="resource-link" href="${safeUrl(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label)}</a>`
      ).join("")}</section>`
    : "";

  const collapsed = loadCollapsed();
  const tilesHtml = pinnedNotes.map(i => {
    const isCollapsed = collapsed.has(i.id);
    return `<details class="resource-tile" data-id="${esc(i.id)}" ${isCollapsed ? "" : "open"}>
      <summary>${esc(i.title)}</summary>
      <div class="resource-tile-body">${md(i.body)}</div>
    </details>`;
  }).join("");

  el.innerHTML =
    `<div class="resources-inner">
      <h3 class="res-heading">Resources</h3>
      ${linksHtml}
      <h3 class="res-heading">Pinned</h3>
      <div class="res-tiles">${tilesHtml || '<p class="muted">No pinned notes.</p>'}</div>
    </div>`;

  // persist per-tile collapse
  el.querySelectorAll("details.resource-tile").forEach(d => {
    d.addEventListener("toggle", () => {
      const set = loadCollapsed();
      const id = d.dataset.id;
      if (d.open) set.delete(id); else set.add(id);
      saveCollapsed(set);
    });
  });
}
