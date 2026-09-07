import { renderRuns, stopRuns } from "./runs.js";
import { renderJobs, stopJobs } from "./jobs.js";
import { api } from "./api.js";
import { md } from "./markdown.js";

let activeType = "task";

const FIELDS = {
  task:      ["title","body","status","priority","tags","parent"],
  objective: ["title","body","status","priority","tags"],
  issue:     ["title","body","status","priority","tags"],
  note:      ["title","body","tags","pinned","links"],
  guardrail: ["title","body","priority","tags"],
};

/* Types where Open/Closed grouping applies. */
const GROUPED_TYPES = new Set(["task", "issue", "objective"]);

const TYPE_LABELS = {
  task: "Tasks",
  objective: "Objectives",
  issue: "Issues",
  note: "Notes",
  guardrail: "Guardrails",
};

const TYPE_KICKERS = {
  task: "Work queue",
  objective: "Outcomes",
  issue: "Risks and blockers",
  note: "Pinned context",
  guardrail: "Operational safety",
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function itemState(i) {
  if (i.type === "guardrail") return "guardrail";
  if (i.status === "done") return "done";
  if (i.status === "blocked") return "blocked";
  if (i.status === "in_progress") return "active";
  return "open";
}

function statusLabel(i) {
  if (i.type === "guardrail") return i.priority || "guardrail";
  if (i.pinned) return "pinned";
  return i.status || i.priority || "open";
}

function renderRow(i) {
  const tags = (i.tags||[]).map(t=>`<span class="item-tag">#${esc(t)}</span>`).join("");
  const priority = i.priority ? `<span class="item-priority">${esc(i.priority)}</span>` : "";
  return `
    <div class="item-row item-${esc(itemState(i))}" data-id="${esc(i.id)}">
      <div class="item-row-main">
        <span class="item-status">${esc(statusLabel(i))}</span>
        <strong>${esc(i.title)}</strong>
      </div>
      <div class="item-row-meta">
        ${priority}
        ${tags}
      </div>
    </div>`;
}

function renderEditor(i) {
  const fields = FIELDS[i.type] || FIELDS.task;
  const f = (k,v)=> fields.includes(k) ? v : "";
  return `
    <div class="item-editor" data-id="${i.id}">
      <div class="item-editor-grid">
        ${f("title",  `<label class="field-wide"><span>Title</span><input name="title" value="${esc(i.title||"")}"></label>`)}
        ${f("status", `<label><span>Status</span><select name="status">
          ${["open","in_progress","blocked","done"].map(s=>`<option ${s===i.status?"selected":""}>${s}</option>`).join("")}
        </select></label>`)}
        ${f("priority", `<label><span>Priority</span><select name="priority">
          ${["low","med","high"].map(s=>`<option ${s===i.priority?"selected":""}>${s}</option>`).join("")}
        </select></label>`)}
        ${f("tags",   `<label class="field-wide"><span>Tags</span><input name="tags" value="${esc((i.tags||[]).join(","))}" placeholder="comma,separated"></label>`)}
        ${f("pinned", `<label class="check-field"><input type="checkbox" name="pinned" ${i.pinned?"checked":""}> <span>pinned</span></label>`)}
        ${f("body",   `<label class="field-wide"><span>Body</span><textarea name="body">${esc(i.body||"")}</textarea></label>`)}
      </div>
      <div class="item-body">${md(i.body)}</div>
      <div class="item-editor-actions">
        <button data-act="save">Save</button>
        <button data-act="delete">Delete</button>
        ${i.type==="task"||i.type==="issue" ? `<button data-act="complete">Complete</button>`:""}
      </div>
    </div>`;
}

function readForm(editor, type) {
  const get = (n)=> editor.querySelector(`[name=${n}]`);
  const out = { type };
  if (get("title")) out.title = get("title").value;
  if (get("body"))  out.body  = get("body").value;
  if (get("status"))   out.status = get("status").value;
  if (get("priority")) out.priority = get("priority").value;
  if (get("tags"))     out.tags = get("tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  if (get("pinned"))   out.pinned = get("pinned").checked;
  return out;
}

function renderGroup(label, items, open) {
  return `
    <details class="item-group" data-group="${label.toLowerCase()}"${open ? " open" : ""}>
      <summary class="item-group-summary">
        <span class="group-label">${esc(label)}</span>
        <span class="group-count">${items.length}</span>
      </summary>
      <div class="item-group-body">
        ${items.length ? items.map(renderRow).join("") : `<div class="item-group-empty">None</div>`}
      </div>
    </details>`;
}

function renderListBody(list, type) {
  if (!GROUPED_TYPES.has(type)) {
    return `<div class="item-card-list">${list.map(renderRow).join("") || `<div class="item-group-empty">None</div>`}</div>`;
  }
  const open   = list.filter(i => i.status !== "done");
  const closed = list.filter(i => i.status === "done");
  return `
    ${renderGroup("Open",   open,   true)}
    ${renderGroup("Closed", closed, false)}`;
}

export async function renderItems(el) {
  const list = await api.list(`?type=${activeType}`);
  const openCount = GROUPED_TYPES.has(activeType)
    ? list.filter(i => i.status !== "done").length
    : list.length;
  const doneCount = GROUPED_TYPES.has(activeType)
    ? list.filter(i => i.status === "done").length
    : 0;
  el.innerHTML = `
    <div class="items-shell">
      <div class="items-hero">
        <div>
          <p class="items-kicker">${esc(TYPE_KICKERS[activeType] || "Dashboard")}</p>
          <h1>${esc(TYPE_LABELS[activeType] || activeType)}</h1>
        </div>
        <div class="items-stats" aria-label="Item counts">
          <span><strong>${openCount}</strong> ${GROUPED_TYPES.has(activeType) ? "open" : "items"}</span>
          ${GROUPED_TYPES.has(activeType) ? `<span><strong>${doneCount}</strong> done</span>` : ""}
        </div>
      </div>
      <div class="items-toolbar">
        <button id="add-item">Add ${esc(activeType)}</button>
      </div>
      ${renderListBody(list, activeType)}
    </div>`;
  el.querySelectorAll(".item-row").forEach(row => {
    row.addEventListener("click", async () => {
      const id = row.dataset.id;
      const item = await api.get(id);
      const ed = document.createElement("div");
      ed.innerHTML = renderEditor(item);
      row.after(ed);
      ed.querySelector("[data-act=save]").addEventListener("click", async () => {
        await api.update(id, readForm(ed, item.type));
        renderItems(el);
      });
      ed.querySelector("[data-act=delete]").addEventListener("click", async () => {
        if (confirm("Delete?")) { await api.remove(id); renderItems(el); }
      });
      const cb = ed.querySelector("[data-act=complete]");
      if (cb) cb.addEventListener("click", async () => { await api.complete(id); renderItems(el); });
    }, { once: true });
  });
  document.getElementById("add-item").addEventListener("click", async () => {
    const created = await api.create({
      type: activeType, title: "(new)",
      ...(activeType==="task"||activeType==="issue" ? {status:"open",priority:"med"} : {}),
      ...(activeType==="guardrail" ? {priority:"high"} : {}),
    });
    renderItems(el);
  });
}

export function bindTabs(itemsEl) {
  document.querySelectorAll("#tabs button").forEach(b => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#tabs button").forEach(x=>x.classList.remove("active"));
      b.classList.add("active");
      const tab = b.dataset.tab;
      if (tab === "runs") {
        stopJobs();
        renderRuns(itemsEl);
      } else if (tab === "jobs") {
        stopRuns();
        renderJobs(itemsEl);
      } else {
        stopRuns();
        stopJobs();
        activeType = tab;
        renderItems(itemsEl);
      }
    });
  });
}
