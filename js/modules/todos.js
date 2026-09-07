/**
 * Helios Dashboard — TODOs Module
 *
 * Renders the active TODO list from todos.json.
 * Exports: renderTodos(data)
 *
 * Data shape: { items: [{ id, status, priority, title, description, tags, created }] }
 *
 * Features:
 *   - Priority-colored dots (🔴 high, 🟡 medium, 🟢 low)
 *   - Expandable descriptions (click title to toggle)
 *   - Tag chips with hover effect
 *   - Sorted by priority (high → medium → low)
 */

import { priorityClass } from './common.js';

/* Priority → emoji dot mapping */
const PRIORITY_DOT = {
  high:   '🔴',
  medium: '🟡',
  low:    '🟢',
};

/* Priority sort weight */
const PRIORITY_WEIGHT = { high: 0, medium: 1, low: 2 };

/**
 * Render a single tag chip.
 * @param {string} tag
 * @returns {string} HTML string
 */
function renderTag(tag) {
  return `<span class="tag-chip" data-tag="${tag}">${tag}</span>`;
}

/**
 * Render the tag list for a todo item.
 * @param {string[]} tags
 * @returns {string} HTML string
 */
function renderTags(tags) {
  if (!tags || tags.length === 0) return '';
  return `<div class="todo-tags">${tags.map(renderTag).join('')}</div>`;
}

/**
 * Escapes HTML entities to protect against accidental injection in JSON strings.
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
 * Render a single todo item.
 * The title is clickable to expand/collapse the description.
 *
 * @param {object} item — { id, status, priority, title, description, tags, created }
 * @returns {string} HTML string
 */
function renderTodoItem(item) {
  const dot  = PRIORITY_DOT[item.priority] || '⚪';
  const pcls = priorityClass(item.priority);   // 'err' | 'warn' | 'info'
  const title = escapeHTML(item.title);
  const desc  = item.description ? escapeHTML(item.description) : '';
  const tags  = renderTags(item.tags);
  const itemId = escapeHTML(item.id);

  return `
    <li class="todo-item todo-priority-${pcls}" data-id="${itemId}">
      <div class="todo-header" onclick="this.parentElement.classList.toggle('expanded')" role="button" tabindex="0" aria-expanded="false">
        <span class="todo-priority" title="${item.priority} priority">${dot}</span>
        <span class="todo-title">${title}</span>
      </div>
      ${desc ? `<div class="todo-desc"><p>${desc}</p></div>` : ''}
      ${tags}
    </li>`;
}

/**
 * Render the full TODO list.
 *
 * @param {object} data — Parsed todos.json shape
 * @param {Array}  data.items — Array of todo item objects
 * @returns {string} HTML string for the TODO section
 */
export function renderTodos(data) {
  if (!data || !Array.isArray(data.items) || data.items.length === 0) {
    return '<div class="todo-list"><p class="empty-state">No active TODOs ✨</p></div>';
  }

  /* Sort by priority: high → medium → low */
  const sorted = [...data.items].sort(
    (a, b) => (PRIORITY_WEIGHT[a.priority] ?? 99) - (PRIORITY_WEIGHT[b.priority] ?? 99)
  );

  const itemsHTML = sorted.map(renderTodoItem).join('');

  return `<ul class="todo-list">${itemsHTML}</ul>`;
}
