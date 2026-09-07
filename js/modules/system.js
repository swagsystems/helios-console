import { api } from "./api.js";

function appendTextEl(parent, tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  parent.appendChild(node);
  return node;
}

function fmtPct(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(0)}%` : "?";
}

function fmtUpdated(value) {
  if (!value) return "updated ?";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `updated ${value}`;
  return `updated ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

function dockerSummary(services) {
  const total = services.length;
  const running = services.filter(svc => String(svc.status || "").toLowerCase().includes("running")).length;
  const healthy = services.filter(svc => String(svc.status || "").toLowerCase().includes("healthy")).length;
  return healthy ? `Docker ${running}/${total} (${healthy} healthy)` : `Docker ${running}/${total}`;
}

export async function renderTopbar(el) {
  // Preserve the resources-toggle button (hardcoded in index.html)
  const toggle = el.querySelector("#resources-toggle");
  el.replaceChildren();
  try {
    const [sys, svc] = await Promise.all([api.system(), api.services()]);
    const lxc = svc.lxc || [];
    const docker = svc.docker || [];
    const up = lxc.filter(l => l.status === "running").length;
    const host = sys.host || {};
    const title = appendTextEl(el, "strong", "", host.name || "helios");
    title.title = [host.kernel, host.uptime ? `uptime ${host.uptime}` : ""].filter(Boolean).join(" · ");
    appendTextEl(el, "span", "topbar-stat", `up ${host.uptime || "?"}`);
    appendTextEl(el, "span", "topbar-stat", `CPU ${fmtPct(host.cpu_usage_pct)}`);
    appendTextEl(el, "span", "topbar-stat", `RAM ${fmtPct(host.ram_pct)}`);
    appendTextEl(el, "span", "topbar-stat", `LXC ${up}/${lxc.length}`);
    appendTextEl(el, "span", "topbar-stat", dockerSummary(docker));
    const dns = appendTextEl(el, "span", "topbar-stat topbar-dns", "DNS DoT");
    dns.title = sys.network?.dns_chain || "DNS chain unavailable";
    appendTextEl(el, "span", "topbar-spacer", "");
    const forge = appendTextEl(el, "a", "topbar-forge", "Forge");
    forge.href = "/forge";
    appendTextEl(el, "span", "topbar-time", fmtUpdated(sys._meta?.updated || svc._meta?.updated));
  } catch (e) {
    appendTextEl(el, "span", "muted", "system data unavailable");
    appendTextEl(el, "span", "topbar-spacer", "");
  }
  if (toggle) el.appendChild(toggle);
}
