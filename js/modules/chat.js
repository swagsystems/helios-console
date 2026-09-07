// Chat page: agent message bus UI.
const TOKEN_KEY = "dashboard_token";
localStorage.removeItem(TOKEN_KEY);

async function login(token) {
  const r = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ token }),
  });
  if (!r.ok) throw new Error(`login -> ${r.status}`);
}

async function sessionActive() {
  const r = await fetch("/api/session", { credentials: "same-origin" });
  return r.ok;
}

async function ensureSession() {
  if (await sessionActive()) return true;
  const dlg = document.getElementById("token-dialog");
  dlg.showModal();
  dlg.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("token-input");
    try {
      await login(input.value.trim());
      location.reload();
    } catch {
      input.value = "";
      input.placeholder = "Invalid token";
      input.focus();
    }
  }, { once: true });
  return false;
}

async function req(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const r = await fetch(path, { method, headers, credentials: "same-origin", body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}`);
  return r.json();
}

const feedEl = document.getElementById("chat-feed");
const formEl = document.getElementById("chat-compose");
const inputEl = document.getElementById("chat-input");
const legendEl = document.getElementById("agent-legend");

let agents = {};        // name -> {color, kind, aliases}
let lastSeenId = null;
let renderedIds = new Set();

function htmlEscape(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function safeColor(color) {
  return /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(color || "") ? color : "#888";
}

function colorFor(name) {
  return safeColor(agents[name]?.color);
}

function renderMentions(body) {
  const escaped = htmlEscape(body);
  return escaped.replace(/(^|[\s(])@([a-zA-Z][\w-]*)/g, (m, pre, name) => {
    const lower = name.toLowerCase();
    const canonical = Object.keys(agents).find(n =>
      n === lower || (agents[n].aliases || []).map(a => a.toLowerCase()).includes(lower)
    ) || lower;
    const c = colorFor(canonical);
    return `${pre}<span class="mention" style="color:${c};border-color:${c}33">@${name}</span>`;
  });
}

function fmtTime(iso) {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const opts = sameDay ? { hour: "2-digit", minute: "2-digit" }
                       : { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" };
  return d.toLocaleString(undefined, opts);
}

function renderMessage(msg) {
  if (renderedIds.has(msg.id)) return;
  renderedIds.add(msg.id);
  const sender = msg.sender || "unknown";
  const senderColor = colorFor(sender);
  const recipients = (msg.recipients || []).map(r =>
    `<span class="mention" style="color:${colorFor(r)};border-color:${colorFor(r)}33">@${htmlEscape(r)}</span>`
  ).join(" ");
  const div = document.createElement("div");
  div.className = "msg";
  div.style.borderLeftColor = senderColor;
  div.innerHTML = `
    <span class="sender" style="color:${senderColor};background:${senderColor}1a">@${htmlEscape(sender)}</span>
    <div class="body">
      ${recipients ? `<span class="recipients"><span class="arrow">→</span>${recipients}</span> ` : ""}
      ${renderMentions(msg.body)}
    </div>
    <span class="ts" title="${htmlEscape(msg.ts)}">${fmtTime(msg.ts)}</span>
  `;
  feedEl.appendChild(div);
}

async function loadAgents() {
  try {
    const list = await req("GET", "/api/agents");
    for (const a of list) agents[a.name] = { ...a, color: safeColor(a.color) };
    legendEl.innerHTML = list.map(a => {
      const color = safeColor(a.color);
      const name = htmlEscape(a.name || "unknown");
      return `<span class="legend-chip"><span class="dot" style="background:${color}"></span>@${name}</span>`;
    }).join("");
  } catch (e) { console.warn("agents load failed", e); }
}

async function poll() {
  try {
    const qs = lastSeenId ? `?since=${encodeURIComponent(lastSeenIso)}` : "?limit=200";
    const list = await req("GET", `/api/messages${qs}`);
    const atBottom = feedEl.scrollHeight - feedEl.scrollTop - feedEl.clientHeight < 80;
    for (const m of list) {
      renderMessage(m);
      lastSeenIso = m.ts;
      lastSeenId = m.id;
    }
    if (atBottom) feedEl.scrollTop = feedEl.scrollHeight;
  } catch (e) { /* token might be wrong; ignore noise */ }
}

let lastSeenIso = null;

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = inputEl.value.trim();
  if (!body) return;
  inputEl.value = "";
  try {
    await req("POST", "/api/messages", { sender: "user", body });
    await poll();
  } catch (err) {
    alert("send failed: " + err.message);
    inputEl.value = body;
  }
});

(async () => {
  if (!(await ensureSession())) return;
  await loadAgents();
  await poll();
  feedEl.scrollTop = feedEl.scrollHeight;
  setInterval(poll, 3000);
})();
