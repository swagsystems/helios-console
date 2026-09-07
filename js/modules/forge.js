import { sessionActive } from "./api.js";

const root = document.getElementById("forge-root");

const state = {
  agents: [],
  jobs: [],
  events: [],
  approvals: [],
  selectedJobId: null,
  loading: true,
  error: "",
  jobFilter: "All",
  command: "",
  message: "",
  setup: {
    mode: "auto",
    job_type: "background",
    selected_agent: "claude",
    cwd: "/root",
    autonomy: "supervised",
  },
  questionPicks: {},
};

let loadInFlight = null;

const DONE_STATUSES = new Set(["completed", "failed", "cancelled", "done", "complete", "error"]);
const RUNNING_STATUSES = new Set(["running", "queued", "waiting"]);

const ICONS = {
  "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
  "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="6" y1="6" x2="18" y2="18"/><line x1="6" y1="18" x2="18" y2="6"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  pause: '<line x1="9" y1="6" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="18"/>',
  play: '<polygon points="6 4 20 12 6 20 6 4"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z"/>',
  terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
  warn: '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>',
  search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  route: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8 6h7a3 3 0 0 1 3 3v6"/>',
  "corner-down-left": '<polyline points="9 10 4 15 9 20"/><path d="M20 4v7a4 4 0 0 1-4 4H4"/>',
  diff: '<path d="M12 2v20"/><path d="M8 6h8M8 18h8"/>',
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function attr(value) {
  return esc(value).replace(/`/g, "&#96;");
}

function icon(name, size = 16, color = "currentColor", strokeWidth = 1.6) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

function button(label, variant = "default", size = "md", data = "", iconName = "", iconRight = "") {
  return `<button class="forge-btn forge-btn-${size} forge-btn-${variant}" ${data}>${iconName ? icon(iconName, size === "lg" ? 16 : 14) : ""}<span>${label}</span>${iconRight ? icon(iconRight, size === "lg" ? 16 : 14) : ""}</button>`;
}

function chip(label, tone = "default", opts = {}) {
  const dot = opts.dot ? `<span class="forge-chip-dot"></span>` : "";
  const mono = opts.mono ? " forge-chip-mono" : "";
  const live = opts.live ? " forge-chip-live" : "";
  const right = opts.iconRight ? icon(opts.iconRight, 11) : "";
  const left = opts.icon && !opts.dot ? icon(opts.icon, 11) : "";
  return `<span class="forge-chip forge-chip-${tone}${mono}${live}">${dot}${left}${esc(label)}${right}</span>`;
}

function kbd(label) {
  return `<span class="forge-kbd">${esc(label)}</span>`;
}

async function req(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return null;
  if (!response.ok) throw new Error(`${method} ${path} -> ${response.status}`);
  return response.json();
}

function selectedJob() {
  return state.jobs.find(job => job.id === state.selectedJobId) || null;
}

function agentByName(name) {
  return state.agents.find(agent => agent.name === name) || null;
}

function agentLabel(name) {
  return agentByName(name)?.label || name || "forge";
}

function agentRole(name) {
  return agentByName(name)?.role || "";
}

function agentColor(name) {
  const color = agentByName(name)?.color || (name === "forge" ? "#c96442" : "#4a5260");
  return /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(color) ? color : "#4a5260";
}

function initials(name) {
  const label = agentLabel(name);
  if (name === "forge" || name === "claude") return icon("sparkle", 14, "#fff", 1.8);
  return esc(label.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase() || "AG");
}

function compactTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit" }).format(date);
}

function relativeTime(iso) {
  if (!iso) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function pendingApprovals() {
  return state.approvals.filter(approval => approval.status === "pending");
}

function owns(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function isEditingField(element = document.activeElement) {
  return ["INPUT", "TEXTAREA", "SELECT"].includes(element?.tagName) || Boolean(element?.isContentEditable);
}

function submitForm(form) {
  if (!form) return;
  if (typeof form.requestSubmit === "function") {
    form.requestSubmit();
    return;
  }
  form.querySelector('[type="submit"]')?.click();
}

function filteredJobs() {
  return state.jobs.filter(job => {
    if (state.jobFilter === "Running") return job.status === "running";
    if (state.jobFilter === "Queued") return job.status === "queued" || job.status === "waiting";
    if (state.jobFilter === "Done") return DONE_STATUSES.has(job.status);
    return true;
  });
}

function jobCounts() {
  return {
    all: state.jobs.length,
    running: state.jobs.filter(job => job.status === "running").length,
    queued: state.jobs.filter(job => job.status === "queued" || job.status === "waiting").length,
    done: state.jobs.filter(job => DONE_STATUSES.has(job.status)).length,
  };
}

function answeredQuestionEventIds() {
  return new Set(
    state.events
      .map(event => event.payload?.answers_for || event.payload?.question_event_id)
      .filter(Boolean)
  );
}

function questionEvents() {
  return state.events.filter(event => Array.isArray(event.payload?.questions));
}

function openQuestionEvent() {
  const answered = answeredQuestionEventIds();
  return [...questionEvents()].reverse().find(event => !answered.has(event.id) && !event.payload?.answered) || null;
}

function lifecycleState() {
  const job = selectedJob();
  if (pendingApprovals().length) return "approval";
  if (openQuestionEvent()) return "questions";
  if (!job) return "done";
  if (DONE_STATUSES.has(job.status)) return "done";
  if (RUNNING_STATUSES.has(job.status)) return "running";
  return "running";
}

function stateChip(stage) {
  if (state.error) return chip("forge error", "danger", { icon: "warn" });
  const job = selectedJob();
  if (job?.status === "failed" || job?.status === "error") return chip("run failed", "danger", { icon: "warn" });
  if (job?.status === "cancelled") return chip("run cancelled", "danger", { icon: "warn" });
  const runningCount = state.jobs.filter(job => job.status === "running").length;
  const pendingCount = pendingApprovals().length;
  if (stage === "questions") return chip("awaiting your input", "warn", { dot: true });
  if (stage === "approval") return chip(`${pendingCount || 1} approval pending`, "warn", { dot: true });
  if (stage === "done") return chip("all clear", "success", { icon: "check" });
  return chip(`${runningCount || state.jobs.length || 0} jobs active`, "accent", { dot: true, live: true });
}

function statusTone(status) {
  if (status === "running") return ["#c96442", true];
  if (status === "queued" || status === "waiting") return ["#c89a4a", false];
  if (status === "completed" || status === "done" || status === "complete") return ["#6aa67f", false];
  if (status === "failed" || status === "error" || status === "cancelled") return ["#c95a4f", false];
  return ["#8b919d", false];
}

function renderHeader(stage, job) {
  const runLabel = job?.dashboard_run_id ? `run_${job.dashboard_run_id.slice(0, 6)}` : "no run";
  return `
    <header class="forge-header">
      <a class="forge-brand" href="/forge.html" aria-label="Forge">
        <span class="forge-mark">${icon("sparkle", 13, "#fff", 2)}</span>
        <span class="forge-brand-name">Forge</span>
        <span class="forge-divider"></span>
        <span class="forge-brand-sub">agent console</span>
      </a>
      <div class="forge-current">
        <span>/</span>
        <span>${esc(job?.title || "new job")}</span>
        <span>·</span>
        <code>${esc(runLabel)}</code>
      </div>
      <div class="forge-header-right">
        ${stateChip(stage)}
        <span class="forge-divider"></span>
        <nav class="forge-nav" aria-label="Dashboard links">
          <a class="forge-btn forge-btn-sm forge-btn-ghost" href="/">Dashboard</a>
          <a class="forge-btn forge-btn-sm forge-btn-ghost" href="/#live-runs">Live runs</a>
          <a class="forge-btn forge-btn-sm forge-btn-ghost" href="/docs">Docs</a>
        </nav>
        <span class="forge-avatar">EL</span>
      </div>
    </header>`;
}

function renderJobsRail() {
  const filter = state.jobFilter;
  const jobs = filteredJobs();
  return `
    <aside class="forge-jobs-rail" aria-label="Forge jobs">
      <div class="forge-rail-top">
        ${button("New job", "accent", "md", 'data-action="new-job"', "plus")}
        <div class="forge-search">${icon("search", 13, "var(--forge-dim)")}<span>Search jobs</span>${kbd("/")}</div>
      </div>
      <div class="forge-tabs">
        ${["All", "Running", "Queued", "Done"].map(tab => `<button class="${tab === filter ? "active" : ""}" data-filter="${attr(tab)}">${tab}</button>`).join("")}
      </div>
      <div class="forge-job-list">
        ${jobs.length ? jobs.map(renderJobButton).join("") : `<div class="forge-empty-card">No ${esc(filter.toLowerCase())} jobs.</div>`}
      </div>
    </aside>`;
}

function renderJobButton(job) {
  const [color, live] = statusTone(job.status);
  const done = DONE_STATUSES.has(job.status) ? " done" : "";
  return `
    <button class="forge-job${job.id === state.selectedJobId ? " active" : ""}${done}" data-job="${attr(job.id)}">
      <span class="forge-job-main">
        <span class="forge-status-dot ${live ? "forge-status-live" : ""}" style="--status-color:${color}"></span>
        <span class="forge-job-title">${esc(job.title)}</span>
        <span class="forge-job-time">${esc(relativeTime(job.updated))}</span>
      </span>
      <span class="forge-job-meta">${esc(agentLabel(job.selected_agent))} · ${esc(job.job_type)} · ${esc(job.mode)}</span>
    </button>`;
}

function renderCommandBar() {
  return `
    <form class="forge-command" data-form="create-job">
      ${icon("chevron-right", 14, "var(--forge-dim)")}
      <textarea name="prompt" rows="1" placeholder="ask forge to audit, build, fix, or supervise..." aria-label="New Forge task">${esc(state.command)}</textarea>
      ${kbd("⌘K")}
      ${button("Send", "accent", "md", 'type="submit"', "", "corner-down-left")}
    </form>`;
}

function renderSetupRibbon() {
  const agents = state.agents.length ? state.agents : [{ name: "claude", label: "Claude" }];
  return `
    <div class="forge-setup">
      <span class="forge-setup-label">setup</span>
      <select name="selected_agent" aria-label="Agent">
        ${agents.map(agent => `<option value="${attr(agent.name)}" ${agent.name === state.setup.selected_agent ? "selected" : ""}>${esc(agent.name)}</option>`).join("")}
      </select>
      <select name="job_type" aria-label="Job type">
        ${["background", "interactive"].map(value => `<option value="${value}" ${value === state.setup.job_type ? "selected" : ""}>${value}</option>`).join("")}
      </select>
      <select name="autonomy" aria-label="Autonomy">
        ${["supervised", "ask", "autonomous"].map(value => `<option value="${value}" ${value === state.setup.autonomy ? "selected" : ""}>${value}</option>`).join("")}
      </select>
      <select name="mode" aria-label="Mode">
        ${["auto", "manual", "suggested"].map(value => `<option value="${value}" ${value === state.setup.mode ? "selected" : ""}>${value}</option>`).join("")}
      </select>
      <input name="cwd" aria-label="Working directory" value="${attr(state.setup.cwd)}" />
      <span class="forge-setup-hint">tap any chip to change</span>
    </div>`;
}

function renderApprovalBanner() {
  const approval = pendingApprovals()[0];
  if (!approval) return "";
  return `
    <div class="forge-approval-banner">
      <div class="forge-banner-title">${icon("pause", 15, "var(--forge-warn)")}<span>${esc(agentLabel(selectedJob()?.selected_agent))} paused - wants approval</span></div>
      <div class="forge-banner-code">${esc(approval.target || approval.action)}</div>
      <div class="forge-banner-actions">
        ${button("Discuss", "ghost", "sm", 'data-action="focus-composer"')}
        ${button("Deny", "outline", "sm", `data-approval="${attr(approval.id)}" data-status="denied"`)}
        ${button("Approve", "accent", "sm", `data-approval="${attr(approval.id)}" data-status="approved"`, "check")}
      </div>
    </div>`;
}

function renderChat(stage, job) {
  return `
    <section class="forge-chat" aria-label="Forge chat">
      ${renderChatHeader(stage, job)}
      <div class="forge-turns">
        ${job ? renderTurns(stage, job) : renderEmpty()}
      </div>
      ${job ? renderComposer(stage) : ""}
    </section>`;
}

function renderChatHeader(stage, job) {
  const failed = job?.status === "failed" || job?.status === "error";
  const cancelled = job?.status === "cancelled";
  const status = {
    questions: chip("waiting", "warn", { dot: true }),
    running: chip("running", "accent", { dot: true, live: true }),
    approval: chip("paused", "warn", { icon: "pause" }),
    done: chip(failed ? "error" : cancelled ? "cancelled" : "complete", failed || cancelled ? "danger" : "success", { icon: failed || cancelled ? "warn" : "check" }),
  }[stage];
  const meta = job ? `${agentLabel(job.selected_agent)} · ${job.cwd} · ${job.dashboard_run_id ? `run_${job.dashboard_run_id.slice(0, 6)}` : "no run"}` : "select or create a job";
  const canStop = job && (stage === "running" || stage === "approval" || job.status === "queued" || job.status === "waiting");
  return `
    <header class="forge-chat-head">
      <h1>${esc(job?.title || "Forge")}</h1>
      ${status}
      <span class="forge-chat-meta">${esc(meta)}</span>
      <div class="forge-chat-actions">
        ${canStop ? button("Stop", "ghost", "sm", 'data-action="stop-job"', "stop") : ""}
        ${job ? button("Delete", "danger", "sm", 'data-action="delete-job"', "x") : ""}
        <button class="forge-icon-btn" data-action="refresh" aria-label="Refresh">${icon("more", 16)}</button>
      </div>
    </header>`;
}

function renderEmpty() {
  return `<div class="forge-empty"><h2>Select or create a job</h2><p>Forge will keep the task, setup questions, chat timeline, tools, approvals, and summary in one surface.</p></div>`;
}

function renderTurns(stage, job) {
  const pieces = [];
  pieces.push(renderBubble({ actor: "you", name: "You", ts: job.created, body: job.prompt }));
  if (!state.events.length) {
    pieces.push(renderBubble({ actor: "forge", name: "forge", ts: job.created, body: "Queued. Waiting for the agent runner to attach.", system: true }));
  }
  for (const event of state.events) {
    if (event.kind === "job_created") continue;
    pieces.push(renderEvent(event));
  }
  if (stage === "done" && !state.events.some(event => event.payload?.summary)) {
    pieces.push(renderFallbackSummary(job));
  }
  if (stage === "running" && state.events.length && !state.events.some(event => event.payload?.streaming)) {
    pieces.push(renderBubble({ actor: "forge", name: "forge", ts: new Date().toISOString(), body: "Watching this run. New tool calls and notes will land here as events arrive.", accent: true, streaming: true }));
  }
  return pieces.join("");
}

function renderEvent(event) {
  if (Array.isArray(event.payload?.questions)) return renderQuestionTurn(event);
  const tool = event.payload?.tool_card || event.payload?.tool;
  if (tool) return renderToolCard(tool);
  if (event.payload?.summary) return renderSummary(event.payload.summary, event);
  if (event.kind === "approval_requested") return renderInlineApproval(event);
  if (event.kind === "approval_resolved") {
    return renderBubble({ actor: event.actor, name: event.actor || "forge", ts: event.ts, body: event.body, system: true });
  }
  const actor = event.actor || "forge";
  return renderBubble({
    actor,
    name: actor === "user" ? "You" : `${agentLabel(actor)}${agentRole(actor) ? ` · ${agentRole(actor)}` : ""}`,
    ts: event.ts,
    body: event.body || event.kind,
    accent: actor === "forge" || actor === "claude",
    system: event.kind === "status" || event.kind === "system",
    streaming: event.payload?.streaming,
  });
}

function renderBubble({ actor, name, ts, body, accent = false, system = false, streaming = false }) {
  const avatarColor = actor === "user" || actor === "you" ? "#4a5260" : agentColor(actor);
  const actorClass = system ? " forge-system" : "";
  return `
    <article class="forge-turn${actorClass}">
      <div class="forge-turn-avatar" style="--avatar-color:${avatarColor}">${initials(actor)}</div>
      <div class="forge-turn-body">
        <div class="forge-turn-meta">
          <span class="forge-turn-name" style="--turn-color:${accent ? "var(--forge-accent)" : "var(--forge-text)"}">${esc(name)}</span>
          <span class="forge-turn-time">${esc(compactTime(ts))}</span>
        </div>
        <div class="forge-turn-text">${esc(body)}${streaming ? '<span class="forge-stream-cursor"></span>' : ""}</div>
      </div>
    </article>`;
}

function renderToolCard(tool) {
  const status = tool.status || "ok";
  const color = status === "running" ? "var(--forge-accent)" : status === "failed" ? "var(--forge-danger)" : "var(--forge-success)";
  return `
    <article class="forge-tool">
      <div class="forge-tool-row" style="--tool-color:${color}">
        <span class="forge-status-dot ${status === "running" ? "forge-status-live" : ""}" style="--status-color:${color}"></span>
        <span class="forge-tool-name">${esc(tool.tool || tool.name || "tool")}</span>
        <span class="forge-tool-target">${esc(tool.target || tool.command || "")}</span>
        ${tool.detail ? `<span class="forge-tool-detail">${esc(tool.detail)}</span>` : ""}
        <span class="forge-tool-ms">${status === "running" ? "· running" : esc(tool.ms || tool.duration || "")}</span>
        ${icon("chevron-down", 12, "var(--forge-dim)")}
      </div>
      ${tool.expanded || tool.body ? `<pre class="forge-tool-body">${esc(tool.body || "")}</pre>` : ""}
    </article>`;
}

function renderQuestionTurn(event) {
  const questions = event.payload.questions || [];
  const answered = answeredQuestionEventIds().has(event.id) || event.payload?.answered;
  const picks = state.questionPicks[event.id] || questions.map(q => Number.isInteger(q.chosen) ? q.chosen : 0);
  if (!state.questionPicks[event.id]) state.questionPicks[event.id] = picks;
  return `
    <article class="forge-turn">
      <div class="forge-turn-avatar" style="--avatar-color:var(--forge-accent)">${icon("sparkle", 14, "#fff", 1.8)}</div>
      <div class="forge-turn-body">
        <div class="forge-turn-meta">
          <span class="forge-turn-name" style="--turn-color:var(--forge-accent)">forge</span>
          <span class="forge-turn-time">${esc(compactTime(event.ts))}</span>
        </div>
        <div class="forge-question-card">
          <div class="forge-question-intro">A few quick questions before I start - pick or just hit ${kbd("↵")} to accept the defaults.</div>
          <div class="forge-question-list">
            ${questions.map((q, index) => renderQuestion(event.id, q, index, picks[index], answered)).join("")}
          </div>
          <div class="forge-question-actions">
            ${button(answered ? "Answers saved" : "Looks good · start", answered ? "default" : "accent", "md", answered ? "disabled" : `data-action="answer-questions" data-event="${attr(event.id)}"`, answered ? "check" : "play")}
            ${button("Chat about it first", "ghost", "md", 'data-action="focus-composer"')}
            <span>${answered ? "kept in chat history" : `${kbd("↵")} to accept all`}</span>
          </div>
        </div>
      </div>
    </article>`;
}

function renderQuestion(eventId, question, index, picked, answered) {
  const options = Array.isArray(question.options) ? question.options : [];
  const label = question.q || question.question || `Question ${index + 1}`;
  return `
    <div>
      <div class="forge-question-title"><span>${index + 1}.</span>${esc(label)}</div>
      <div class="forge-options">
        ${options.map((option, optionIndex) => `
          <button class="forge-option ${picked === optionIndex ? "picked" : ""}" data-action="pick-question" data-event="${attr(eventId)}" data-question="${index}" data-option="${optionIndex}" ${answered ? "disabled" : ""}>
            ${picked === optionIndex ? icon("check", 11, "#fff", 2.4) : ""}${esc(option)}
          </button>`).join("")}
      </div>
    </div>`;
}

function renderInlineApproval(event) {
  const approvalId = event.payload?.approval_id;
  const approval = state.approvals.find(item => item.id === approvalId);
  const pending = approval?.status === "pending";
  return `
    <article class="forge-inline-approval">
      <div class="forge-inline-title">${icon("warn", 15, "var(--forge-warn)")}<span>Paused for approval</span>${chip(event.actor || "forge", "warn", { mono: true })}</div>
      <div class="forge-inline-code">${esc(approval?.target || event.body)}</div>
      <div class="forge-inline-actions">
        ${pending ? button("Approve & continue", "accent", "sm", `data-approval="${attr(approval.id)}" data-status="approved"`, "check") : ""}
        ${pending ? button("Deny", "outline", "sm", `data-approval="${attr(approval.id)}" data-status="denied"`, "x") : ""}
        ${button("Discuss in chat", "ghost", "sm", 'data-action="focus-composer"')}
      </div>
    </article>`;
}

function renderSummary(summary, event) {
  const chips = Array.isArray(summary.chips) ? summary.chips : [];
  const items = Array.isArray(summary.items) ? summary.items : Array.isArray(summary.changes) ? summary.changes : [];
  const tone = summary.status === "failed" ? "warn" : "success";
  return `
    <article class="forge-turn">
      <div class="forge-turn-avatar" style="--avatar-color:${tone === "success" ? "var(--forge-success)" : "var(--forge-danger)"}">${icon(tone === "success" ? "check" : "warn", 14, "#fff", 1.8)}</div>
      <div class="forge-turn-body">
        <div class="forge-turn-meta">
          <span class="forge-turn-name" style="--turn-color:${tone === "success" ? "var(--forge-success)" : "var(--forge-danger)"}">forge · summary</span>
          <span class="forge-turn-time">${esc(compactTime(event.ts))}</span>
        </div>
        <div class="forge-summary-card">
          <div class="forge-summary-title">${icon(tone === "success" ? "check" : "warn", 16, tone === "success" ? "var(--forge-success)" : "var(--forge-danger)", 2.2)}<span>${esc(summary.title || "Run complete")}</span></div>
          <div class="forge-summary-chips">${chips.map(item => chip(item, tone === "success" ? "success" : "warn")).join("")}</div>
          ${items.length ? `<h3>What changed</h3><ul>${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : `<div class="forge-turn-text">${esc(summary.body || "No summary details yet.")}</div>`}
          <div class="forge-summary-actions">
            ${button("View diff", "default", "sm", "", "diff")}
            ${button("Run log", "ghost", "sm", "", "terminal")}
            <span class="forge-chat-meta" style="margin-left:auto">${esc(selectedJob()?.dashboard_run_id ? `run_${selectedJob().dashboard_run_id.slice(0, 6)}` : "")}</span>
          </div>
        </div>
      </div>
    </article>`;
}

function renderFallbackSummary(job) {
  const failed = job.status === "failed" || job.status === "error" || job.status === "cancelled";
  const error = job.runner_error ? `Runner error: ${job.runner_error}` : "Review the chat timeline and linked dashboard run for details.";
  return renderSummary({
    status: failed ? "failed" : "completed",
    title: failed ? `Run ended: ${job.status}` : "Forge job complete",
    chips: [job.status, agentLabel(job.selected_agent), job.job_type],
    items: failed ? [error] : ["Review the chat timeline for changes and verification notes."],
  }, { ts: job.updated });
}

function renderComposer(stage) {
  const job = selectedJob();
  const failed = job?.status === "failed" || job?.status === "error" || job?.status === "cancelled";
  const placeholder = {
    questions: "Or just chat - I can ask follow-ups instead...",
    running: "Message forge mid-stream - I'll fold it in",
    approval: "Discuss the pending approval, or override...",
    done: "Ask a follow-up, or start a new job (⌘N)...",
  }[stage];
  const footer = {
    questions: '<span style="color:var(--forge-warn)">● waiting on your answers</span>',
    running: '<span style="color:var(--forge-accent)">● streaming · forge · tools appear here</span>',
    approval: '<span style="color:var(--forge-warn)">● paused · approval needed to continue</span>',
    done: failed ? '<span style="color:var(--forge-danger)">△ ended · review error details</span>' : '<span style="color:var(--forge-success)">✓ complete · ready for follow-up</span>',
  }[stage];
  return `
    <form class="forge-composer" data-form="message">
      <div class="forge-composer-box">
        <input name="body" value="${attr(state.message)}" placeholder="${attr(placeholder)}" aria-label="Forge chat message" />
        <div class="forge-composer-actions">
          ${chip("as user", "muted", { iconRight: "chevron-down" })}
          ${button("Send", "accent", "md", 'type="submit"', "send")}
        </div>
      </div>
      <div class="forge-composer-footer">
        ${footer}
        <span>${kbd("⌘↵")} send · ${kbd("⌘K")} command</span>
      </div>
    </form>`;
}

function renderRightRail(stage, job) {
  return `
    <aside class="forge-right-rail" aria-label="Forge context">
      <section class="forge-rail-section">
        <div class="forge-section-head">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="forge-section-label">Approvals</span>
            ${pendingApprovals().length ? chip(`${pendingApprovals().length} pending`, "warn", { dot: true }) : ""}
          </div>
          ${button("Request", "ghost", "sm", 'data-action="request-approval"')}
        </div>
        <div class="forge-approval-list">
          ${state.approvals.length ? state.approvals.map(renderApprovalCard).join("") : `<div class="forge-empty-card">No approvals pending</div>`}
        </div>
      </section>
      <section class="forge-rail-section">
        <div class="forge-section-head">
          <span class="forge-section-label">Routing</span>
          ${chip(`${state.agents.length} agents`, "muted", { icon: "route" })}
        </div>
        <div class="forge-agent-list">
          ${(state.agents.length ? state.agents : fallbackAgents()).map(agent => renderAgentCard(agent, job)).join("")}
        </div>
      </section>
    </aside>`;
}

function renderApprovalCard(approval) {
  const pending = approval.status === "pending";
  return `
    <article class="forge-approval-card ${pending ? "" : "resolved"}">
      <div class="forge-approval-meta">
        ${chip(approval.authority || "user", pending ? "warn" : "muted", { mono: true })}
        <span class="forge-turn-time">${esc(compactTime(approval.created))}</span>
        <span style="margin-left:auto">${chip(approval.status, pending ? "warn" : approval.status === "approved" ? "success" : "muted")}</span>
      </div>
      <p>${esc(approval.action)}</p>
      <div class="forge-approval-target">${esc(approval.target || "No target specified")}</div>
      ${pending ? `<div class="forge-approval-actions">${button("Approve", "accent", "sm", `data-approval="${attr(approval.id)}" data-status="approved"`, "check")}${button("Deny", "outline", "sm", `data-approval="${attr(approval.id)}" data-status="denied"`)}</div>` : ""}
    </article>`;
}

function renderAgentCard(agent, job) {
  const active = job?.selected_agent === agent.name || (!job && agent.name === state.setup.selected_agent);
  return `
    <article class="forge-agent-card ${active ? "active" : ""}" style="--agent-color:${attr(agent.color || "#c96442")}">
      <div class="forge-agent-row">
        <span class="forge-agent-name">${esc(agent.label || agent.name)}</span>
        <span class="forge-agent-role">${esc(agent.role || "")}</span>
        ${active ? chip("active", "accent") : ""}
      </div>
      <div class="forge-agent-desc">${esc(agent.description || "")}</div>
    </article>`;
}

function fallbackAgents() {
  return [
    { name: "claude", role: "orchestrator", label: "Claude", description: "Routes work and manages approvals.", color: "#c96442" },
    { name: "codex", role: "worker", label: "Codex", description: "Repo, terminal, and implementation worker.", color: "#5a8fd4" },
  ];
}

function render() {
  const job = selectedJob();
  const stage = lifecycleState();
  root.innerHTML = `
    <div class="forge-app">
      ${renderHeader(stage, job)}
      <div class="forge-shell">
        ${renderJobsRail()}
        <main class="forge-main">
          ${state.error ? `<div class="forge-approval-banner"><div class="forge-banner-title">${icon("warn", 15, "var(--forge-danger)")}<span>${esc(state.error)}</span></div></div>` : ""}
          ${renderCommandBar()}
          ${renderSetupRibbon()}
          ${renderMobileJobPicker(job)}
          ${renderMobileControls(stage, job)}
          ${stage === "approval" ? renderApprovalBanner() : ""}
          ${renderChat(stage, job)}
        </main>
        ${renderRightRail(stage, job)}
      </div>
    </div>`;
}

function renderMobileJobPicker(job) {
  if (!state.jobs.length) return "";
  const jobs = filteredJobs();
  const visibleJobs = jobs.length ? jobs : state.jobs;
  return `
    <label class="forge-mobile-job-picker">
      <span class="forge-section-label">job</span>
      <select name="mobile_job" aria-label="Selected Forge job">
        ${visibleJobs.map(item => `<option value="${attr(item.id)}" ${item.id === job?.id ? "selected" : ""}>${esc(item.title)} · ${esc(item.status)}</option>`).join("")}
      </select>
    </label>`;
}

function renderMobileControls(stage, job) {
  if (!state.jobs.length) return "";
  const counts = jobCounts();
  const tabs = [
    ["All", counts.all],
    ["Running", counts.running],
    ["Queued", counts.queued],
    ["Done", counts.done],
  ];
  const selectedVisible = filteredJobs().some(item => item.id === job?.id) || state.jobFilter === "All";
  return `
    <section class="forge-mobile-controls" aria-label="Mobile Forge controls">
      <div class="forge-mobile-tabs" role="tablist" aria-label="Job status filters">
        ${tabs.map(([tab, count]) => `<button class="${tab === state.jobFilter ? "active" : ""}" data-filter="${attr(tab)}" type="button">${esc(tab)}<span>${count}</span></button>`).join("")}
      </div>
      <div class="forge-mobile-context">
        <span>${chip(agentLabel(job?.selected_agent || state.setup.selected_agent), "muted", { icon: "route" })}</span>
        <span>${chip(stage === "approval" ? "approval" : job?.status || "ready", stage === "approval" ? "warn" : job?.status === "running" ? "accent" : DONE_STATUSES.has(job?.status) ? "success" : "muted")}</span>
        ${!selectedVisible ? `<span class="forge-mobile-note">selected job is outside this filter</span>` : ""}
        ${button(pendingApprovals().length ? `${pendingApprovals().length} pending` : "Request", pendingApprovals().length ? "outline" : "default", "sm", 'data-action="request-approval"', pendingApprovals().length ? "pause" : "")}
      </div>
    </section>`;
}

async function load({ keepSelection = true, force = false } = {}) {
  if (!force && isEditingField()) return;
  if (loadInFlight) {
    await loadInFlight;
    if (!force) return;
  }
  loadInFlight = loadInner({ keepSelection });
  try {
    return await loadInFlight;
  } finally {
    loadInFlight = null;
  }
}

async function loadInner({ keepSelection = true } = {}) {
  try {
    const [agents, jobs] = await Promise.all([
      req("GET", "/api/forge/agents"),
      req("GET", "/api/forge/jobs?limit=100"),
    ]);
    state.agents = agents;
    state.jobs = jobs;
    if (!state.setup.selected_agent && agents[0]) state.setup.selected_agent = agents[0].name;
    if (!keepSelection || !state.selectedJobId || !jobs.some(job => job.id === state.selectedJobId)) {
      state.selectedJobId = jobs[0]?.id || null;
    }
    await loadSelectedDetail();
    state.error = "";
  } catch (error) {
    state.error = error.message;
  } finally {
    state.loading = false;
    render();
  }
}

async function loadSelectedDetail() {
  if (!state.selectedJobId) {
    state.events = [];
    state.approvals = [];
    return;
  }
  const [events, approvals] = await Promise.all([
    req("GET", `/api/forge/jobs/${state.selectedJobId}/events`),
    req("GET", `/api/forge/jobs/${state.selectedJobId}/approvals`),
  ]);
  state.events = events;
  state.approvals = approvals;
}

async function selectJob(jobId) {
  state.selectedJobId = jobId;
  await loadSelectedDetail();
  render();
}

async function createJob(form) {
  const prompt = new FormData(form).get("prompt").trim();
  if (!prompt) return;
  const selected_agent = state.setup.mode === "auto" ? state.setup.selected_agent : state.setup.selected_agent;
  const job = await req("POST", "/api/forge/jobs", {
    prompt,
    mode: state.setup.mode,
    selected_agent,
    job_type: state.setup.job_type,
    cwd: state.setup.cwd || "/root",
    autonomy: state.setup.autonomy,
  });
  state.command = "";
  await load({ keepSelection: false, force: true });
  await selectJob(job.id);
}

async function sendMessage(form) {
  if (!state.selectedJobId) return;
  const body = new FormData(form).get("body").trim();
  if (!body) return;
  await req("POST", `/api/forge/jobs/${state.selectedJobId}/events`, {
    kind: "user_message",
    actor: "user",
    body,
    payload: {},
  });
  state.message = "";
  await loadSelectedDetail();
  render();
}

async function answerQuestions(eventId) {
  const event = state.events.find(item => item.id === eventId);
  if (!event) return;
  const questions = event.payload.questions || [];
  const picks = state.questionPicks[eventId] || questions.map(q => q.chosen ?? 0);
  const answers = {};
  questions.forEach((question, index) => {
    const key = question.id || question.key || `q${index + 1}`;
    answers[key] = (question.options || [])[picks[index]] ?? "";
  });
  await req("POST", `/api/forge/jobs/${state.selectedJobId}/events`, {
    kind: "user_message",
    actor: "user",
    body: "Answered setup questions.",
    payload: { answers_for: eventId, answers },
  });
  await req("PATCH", `/api/forge/jobs/${state.selectedJobId}`, { status: "running" });
  await load({ force: true });
}

async function resolveApproval(id, status) {
  await req("PATCH", `/api/forge/approvals/${id}`, {
    status,
    reviewer: "user",
    note: `Request ${status} from Forge UI.`,
  });
  await load({ force: true });
}

async function stopJob() {
  if (!state.selectedJobId) return;
  await req("POST", `/api/forge/jobs/${state.selectedJobId}/stop`);
  await load({ force: true });
}

async function deleteJob() {
  const job = selectedJob();
  const active = job && !DONE_STATUSES.has(job.status);
  const message = active ? "Delete and stop this running Forge job?" : "Delete this Forge job?";
  if (!state.selectedJobId || !confirm(message)) return;
  await req("DELETE", `/api/forge/jobs/${state.selectedJobId}`);
  state.selectedJobId = null;
  await load({ keepSelection: false, force: true });
}

async function requestApproval() {
  if (!state.selectedJobId) return;
  await req("POST", `/api/forge/jobs/${state.selectedJobId}/approvals`, {
    action: "Approve next supervised action",
    risk: "medium",
    authority: "user",
    target: "Current Forge job",
    rollback: "Pause the job and use the linked dashboard run resume context.",
  });
  await load({ force: true });
}

root.addEventListener("submit", async event => {
  event.preventDefault();
  try {
    if (event.target.dataset.form === "create-job") await createJob(event.target);
    if (event.target.dataset.form === "message") await sendMessage(event.target);
  } catch (error) {
    state.error = error.message;
    render();
  }
});

root.addEventListener("input", event => {
  if (event.target.matches(".forge-command textarea")) state.command = event.target.value;
  if (event.target.matches(".forge-composer input")) state.message = event.target.value;
  if (event.target.name && owns(state.setup, event.target.name)) {
    state.setup[event.target.name] = event.target.value;
  }
});

root.addEventListener("change", event => {
  if (event.target.name === "mobile_job") {
    selectJob(event.target.value);
    return;
  }
  if (event.target.name && owns(state.setup, event.target.name)) {
    state.setup[event.target.name] = event.target.value;
    render();
  }
});

root.addEventListener("click", async event => {
  const jobButton = event.target.closest("[data-job]");
  const filterButton = event.target.closest("[data-filter]");
  const action = event.target.closest("[data-action]");
  const approval = event.target.closest("[data-approval]");
  try {
    if (jobButton) {
      await selectJob(jobButton.dataset.job);
      return;
    }
    if (filterButton) {
      state.jobFilter = filterButton.dataset.filter;
      render();
      return;
    }
    if (approval) {
      await resolveApproval(approval.dataset.approval, approval.dataset.status);
      return;
    }
    if (!action) return;
    if (action.dataset.action === "new-job") {
      state.command = "";
      render();
      root.querySelector(".forge-command textarea")?.focus();
    }
    if (action.dataset.action === "refresh") await load({ force: true });
    if (action.dataset.action === "focus-composer") root.querySelector(".forge-composer input")?.focus();
    if (action.dataset.action === "stop-job") await stopJob();
    if (action.dataset.action === "delete-job") await deleteJob();
    if (action.dataset.action === "request-approval") await requestApproval();
    if (action.dataset.action === "answer-questions") await answerQuestions(action.dataset.event);
    if (action.dataset.action === "pick-question") {
      const eventId = action.dataset.event;
      const q = Number(action.dataset.question);
      const option = Number(action.dataset.option);
      const eventItem = state.events.find(item => item.id === eventId);
      const length = eventItem?.payload?.questions?.length || 0;
      const picks = state.questionPicks[eventId] || Array.from({ length }, () => 0);
      picks[q] = option;
      state.questionPicks[eventId] = picks;
      render();
    }
  } catch (error) {
    state.error = error.message;
    render();
  }
});

document.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    root.querySelector(".forge-command textarea")?.focus();
  }
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    submitForm(root.querySelector(".forge-composer"));
  }
  if (event.key === "Enter" && lifecycleState() === "questions" && document.activeElement?.tagName !== "TEXTAREA" && document.activeElement?.tagName !== "INPUT") {
    const open = openQuestionEvent();
    if (open) answerQuestions(open.id);
  }
});

(async () => {
  if (!(await sessionActive())) {
    window.location.href = "/api/session/login";
    return;
  }
  await load();
  setInterval(() => load().catch(() => {}), 5000);
})();
