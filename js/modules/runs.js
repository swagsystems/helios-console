async function fetchRuns(status, limit = 50) {
  const qs = status ? `?status=${status}&limit=${limit}` : `?limit=${limit}`;
  const r = await fetch(`/api/runs${qs}`, { credentials: "same-origin" });
  if (!r.ok) throw new Error(`runs list ${r.status}`);
  return r.json();
}

async function fetchRunCounts() {
  const r = await fetch("/api/runs/counts", { credentials: "same-origin" });
  if (!r.ok) throw new Error(`runs counts ${r.status}`);
  return r.json();
}

async function authedFetch(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const r = await fetch(path, { method, headers, credentials: "same-origin", body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}`);
  if (r.status === 204) return null;
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

const STEP_GLYPH = {
  done: "✓", in_progress: "→", failed: "✕",
  skipped: "–", pending: "·",
};

const RUN_LABEL = {
  active: "Active", stalled: "Stalled", completed: "Completed",
  failed: "Failed", abandoned: "Abandoned",
};

function ageString(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return `${Math.floor(ms/1000)}s ago`;
  if (ms < 3600_000) return `${Math.floor(ms/60_000)}m ago`;
  if (ms < 86400_000) return `${Math.floor(ms/3600_000)}h ago`;
  return `${Math.floor(ms/86400_000)}d ago`;
}

function isStale(run) {
  if (run.status !== "active") return false;
  return Date.now() - new Date(run.last_heartbeat).getTime() > 5 * 60 * 1000;
}

function runState(run) {
  return isStale(run) ? "stale" : run.status;
}

function runLabel(run) {
  return isStale(run) ? "No heartbeat" : RUN_LABEL[run.status] || run.status;
}

function progress(run) {
  const steps = run.steps || [];
  if (!steps.length) return 0;
  const finished = steps.filter(s => ["done", "failed", "skipped"].includes(s.status)).length;
  return Math.round((finished / steps.length) * 100);
}

function compactDate(iso) {
  try {
    return new Intl.DateTimeFormat([], {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    }).format(new Date(iso));
  } catch (_) {
    return iso || "";
  }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

function providerModelLabel(run) {
  const provider = run.provider || "unknown";
  return run.model ? `${provider}/${run.model}` : provider;
}

function renderStepOutput(output, persistKey) {
  if (!output) return "";
  const text = String(output);
  const isLong = text.length > 180 || text.includes("\n");
  if (!isLong) return `<span class="step-out">${escapeHtml(text)}</span>`;
  const preview = text.replace(/\s+/g, " ").trim().slice(0, 180);
  return `
    <details class="step-out step-output-full" data-persist-open="${escapeHtml(persistKey)}">
      <summary>
        <span class="step-output-preview">${escapeHtml(preview)}${text.length > preview.length ? "..." : ""}</span>
        <span class="step-output-chip">View full</span>
      </summary>
      <pre>${escapeHtml(text)}</pre>
    </details>`;
}

function captureOpenDetails(root) {
  return new Set(
    [...root.querySelectorAll("details[data-persist-open][open]")]
      .map(detail => detail.dataset.persistOpen)
      .filter(Boolean),
  );
}

function restoreOpenDetails(root, openKeys) {
  root.querySelectorAll("details[data-persist-open]").forEach(detail => {
    detail.open = openKeys.has(detail.dataset.persistOpen);
  });
}

function renderRun(run) {
  const state = runState(run);
  const pct = progress(run);
  const steps = (run.steps || []).map((s, idx) => {
    const cls = s.status === "in_progress" ? "step-active" : `step-${s.status}`;
    const out = renderStepOutput(s.output, `${run.id}:step:${idx}`);
    return `
      <li class="${cls}">
        <span class="step-mark" aria-hidden="true">${STEP_GLYPH[s.status] || "·"}</span>
        <span class="step-main">
          <span class="step-title">${escapeHtml(s.title)}</span>
          ${out}
        </span>
      </li>`;
  }).join("");
  const ctx = run.context_blob && Object.keys(run.context_blob).length
    ? `<details class="run-ctx" data-persist-open="${escapeHtml(`${run.id}:context`)}"><summary>resume context</summary><pre>${escapeHtml(JSON.stringify(run.context_blob, null, 2))}</pre></details>`
    : "";
  return `
    <article class="run-card run-${escapeHtml(state)}" data-id="${escapeHtml(run.id)}">
      <header class="run-card-head">
        <div class="run-title-block">
          <span class="run-badge">${escapeHtml(runLabel(run))}</span>
          <strong>${escapeHtml(run.goal)}</strong>
        </div>
        <div class="run-meta-stack">
          <span>${escapeHtml(providerModelLabel(run))}</span>
          <span title="${escapeHtml(run.last_heartbeat || "")}">heartbeat ${ageString(run.last_heartbeat)}</span>
        </div>
      </header>
      <div class="run-progress" aria-label="Run progress ${pct}%">
        <span style="width:${pct}%"></span>
      </div>
      <div class="run-submeta">
        <code>${escapeHtml(run.id)}</code>
        <span>updated ${escapeHtml(compactDate(run.updated || run.last_heartbeat))}</span>
      </div>
      <ol class="run-steps">${steps || '<li class="step-pending">· no steps yet</li>'}</ol>
      ${ctx}
      <div class="run-actions">
        <button data-act="copy-resume">Copy resume prompt</button>
        ${run.status === "active" ? `<button data-act="abandon">Abandon</button>` : ""}
        ${run.status !== "active" ? `<button data-act="delete">Delete</button>` : ""}
      </div>
    </article>`;
}

function renderRunSection(title, runs, empty, modifier = "") {
  return `
    <section class="runs-section ${modifier}">
      <div class="runs-section-head">
        <h2>${escapeHtml(title)}</h2>
        <span>${runs.length}</span>
      </div>
      ${runs.length
        ? `<div class="runs-grid">${runs.map(renderRun).join("")}</div>`
        : `<p class="runs-empty">${empty}</p>`}
    </section>`;
}

function renderRunsShell({ active, finished, previous, counts, showAllRuns }) {
  return `
    <div class="runs-shell">
      <div class="runs-hero">
        <div>
          <p class="runs-kicker">Agent execution</p>
          <h1>Live runs</h1>
        </div>
        <div class="runs-stats" aria-label="Run counts">
          <span class="runs-stat"><strong>${active.length}</strong> live</span>
          <span class="runs-stat"><strong>${finished.length}</strong> recent</span>
          <button class="runs-stat runs-stat-button" type="button" data-act="toggle-all-runs" aria-expanded="${showAllRuns ? "true" : "false"}">
            <strong>${counts.total}</strong> total
          </button>
        </div>
      </div>
      ${renderRunSection("Active runs", active, 'No active runs. Agents call <code>start_run</code> to appear here.', "runs-section-active")}
      ${renderRunSection("Recent", finished, "No recent runs.", "runs-section-recent")}
      ${showAllRuns ? renderRunSection("All previous runs", previous, "No previous runs.", "runs-section-all") : ""}
    </div>`;
}

function bindActions(el) {
  el.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    try {
      if (act === "toggle-all-runs") {
        showAllRuns = !showAllRuns;
        await render(el);
        return;
      }
      const card = btn.closest("article.run-card");
      const id = card?.dataset.id;
      if (!id) return;
      if (act === "copy-resume") {
        const respText = await authedFetch("GET", `/api/runs/${id}/resume`);
        const ok = await copyToClipboard(respText);
        if (ok) {
          btn.textContent = "Copied!";
          setTimeout(() => { btn.textContent = "Copy resume prompt"; }, 1500);
        } else {
          showResumeDialog(respText);
        }
      } else if (act === "abandon") {
        await authedFetch("PATCH", `/api/runs/${id}`, { status: "abandoned" });
        await render(el);
      } else if (act === "delete") {
        if (!confirm("Delete this run permanently?")) return;
        await authedFetch("DELETE", `/api/runs/${id}`);
        await render(el);
      }
    } catch (err) {
      alert(err.message);
    }
  });
}


async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) { /* fall through */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.setAttribute("readonly", "");
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (_) {
    return false;
  }
}

function showResumeDialog(text) {
  let dlg = document.getElementById("resume-dialog");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "resume-dialog";
    dlg.innerHTML = `
      <form method="dialog" style="display:flex;flex-direction:column;gap:0.5em;min-width:min(640px,90vw)">
        <p style="margin:0;color:#aaa">Auto-copy blocked (insecure context). Select all and copy manually:</p>
        <textarea readonly style="width:100%;height:50vh;background:#0c0c0c;color:#ddd;border:1px solid #333;padding:0.5em;font-family:monospace;font-size:0.85em"></textarea>
        <div style="display:flex;gap:0.5em;justify-content:flex-end">
          <button type="button" data-act="select-all">Select all</button>
          <button value="close">Close</button>
        </div>
      </form>`;
    document.body.appendChild(dlg);
    dlg.querySelector("[data-act=select-all]").addEventListener("click", () => {
      const t = dlg.querySelector("textarea");
      t.focus(); t.select();
    });
  }
  const ta = dlg.querySelector("textarea");
  ta.value = text;
  dlg.showModal();
  setTimeout(() => { ta.focus(); ta.select(); }, 50);
}

let pollTimer = null;
let showAllRuns = false;

async function render(el) {
  try {
    const openDetails = captureOpenDetails(el);
    const [active, recent, counts] = await Promise.all([
      fetchRuns("active"),
      fetchRuns(),
      fetchRunCounts(),
    ]);
    const activeIds = new Set(active.map(r => r.id));
    const finished = recent.filter(r => !activeIds.has(r.id)).slice(0, 10);
    let previous = [];
    if (showAllRuns) {
      const allRuns = await fetchRuns(null, Math.max(counts.total, 50));
      previous = allRuns.filter(r => !activeIds.has(r.id));
    }
    el.innerHTML = renderRunsShell({ active, finished, previous, counts, showAllRuns });
    restoreOpenDetails(el, openDetails);
  } catch (e) {
    el.innerHTML = `<p class="muted">Error loading runs: ${escapeHtml(e.message)}</p>`;
  }
}

export function renderRuns(el) {
  if (pollTimer) clearInterval(pollTimer);
  bindActions(el);
  render(el);
  pollTimer = setInterval(() => render(el), 3000);
}

export function stopRuns() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}
