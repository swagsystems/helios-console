async function req(method, path) {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
  });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}`);
  return r.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
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

const JOB_STATE = {
  queued: "Queued",
  running: "Running",
  waiting: "Waiting",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

function renderJob(job) {
  return `
    <article class="job-card job-${esc(job.status)}">
      <header class="job-card-head">
        <div>
          <span class="job-badge">${esc(JOB_STATE[job.status] || job.status || "Unknown")}</span>
          <h2>${esc(job.title)}</h2>
        </div>
        <a href="/forge" class="job-open">Open in Forge</a>
      </header>
      <p>${esc(job.prompt)}</p>
      <dl class="job-meta">
        <div><dt>Agent</dt><dd>${esc(job.selected_agent)}</dd></div>
        <div><dt>Mode</dt><dd>${esc(job.mode)}</dd></div>
        <div><dt>Type</dt><dd>${esc(job.job_type)}</dd></div>
        <div><dt>Autonomy</dt><dd>${esc(job.autonomy)}</dd></div>
        <div><dt>CWD</dt><dd><code>${esc(job.cwd)}</code></dd></div>
        <div><dt>Run</dt><dd><code>${esc(job.dashboard_run_id || "none")}</code></dd></div>
      </dl>
      <footer class="job-card-foot">
        <span>created ${esc(compactDate(job.created))}</span>
        <span>updated ${esc(compactDate(job.updated))}</span>
      </footer>
    </article>`;
}

function renderSection(title, jobs, empty) {
  return `
    <section class="jobs-section">
      <div class="jobs-section-head">
        <h2>${esc(title)}</h2>
        <span>${jobs.length}</span>
      </div>
      ${jobs.length ? `<div class="jobs-grid">${jobs.map(renderJob).join("")}</div>` : `<p class="jobs-empty">${empty}</p>`}
    </section>`;
}

async function render(el) {
  try {
    const jobs = await req("GET", "/api/forge/jobs?limit=100");
    const active = jobs.filter(job => !["completed", "failed", "cancelled"].includes(job.status));
    const finished = jobs.filter(job => ["completed", "failed", "cancelled"].includes(job.status));
    el.innerHTML = `
      <div class="jobs-shell">
        <div class="jobs-hero">
          <div>
            <p class="jobs-kicker">Forge control plane</p>
            <h1>Jobs</h1>
          </div>
          <div class="jobs-stats" aria-label="Job counts">
            <span><strong>${active.length}</strong> active</span>
            <span><strong>${finished.length}</strong> finished</span>
            <a href="/forge">New job</a>
          </div>
        </div>
        ${renderSection("Active jobs", active, "No active Forge jobs.")}
        ${renderSection("Finished jobs", finished.slice(0, 20), "No finished Forge jobs.")}
      </div>`;
  } catch (e) {
    el.innerHTML = `<p class="muted">Error loading jobs: ${esc(e.message)}</p>`;
  }
}

let pollTimer = null;

export function renderJobs(el) {
  if (pollTimer) clearInterval(pollTimer);
  render(el);
  pollTimer = setInterval(() => render(el), 5000);
}

export function stopJobs() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}
