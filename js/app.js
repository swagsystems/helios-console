import { renderTopbar } from "./modules/system.js?v=2";
import { renderResources } from "./modules/resources.js?v=2";
import { login, sessionActive } from "./modules/api.js";
import { renderItems, bindTabs } from "./modules/items.js";

async function ensureSession() {
  if (await sessionActive()) return true;
  const dlg = document.getElementById("token-dialog");
  if (!dlg) return false;
  dlg.showModal();
  dlg.querySelector("form")?.addEventListener("submit", async (e) => {
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
  });
  return false;
}

async function boot() {
  if (!(await ensureSession())) return;
  renderTopbar(document.getElementById("topbar"));
  renderResources(document.getElementById("resources"));
  const itemsEl = document.getElementById("items");
  bindTabs(itemsEl);
  renderItems(itemsEl);

  // Sidebar collapse — works on desktop AND mobile, persists in localStorage
  const SIDEBAR_KEY = "dash.sidebar.collapsed";
  const body = document.body;
  const resToggle = document.getElementById("resources-toggle");

  const isMobile = () => window.matchMedia("(max-width: 768px)").matches;

  const applySidebarState = () => {
    const collapsed = localStorage.getItem(SIDEBAR_KEY) === "1";
    if (isMobile()) {
      // Mobile: drawer pattern — closed by default, opened by toggle
      body.classList.remove("sidebar-collapsed");
      body.classList.toggle("show-resources", false);
    } else {
      body.classList.toggle("sidebar-collapsed", collapsed);
      body.classList.remove("show-resources");
    }
    if (resToggle) {
      resToggle.setAttribute("aria-expanded", isMobile()
        ? body.classList.contains("show-resources") ? "true" : "false"
        : collapsed ? "false" : "true");
    }
  };

  if (resToggle) {
    resToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      if (isMobile()) {
        const open = body.classList.toggle("show-resources");
        resToggle.setAttribute("aria-expanded", open ? "true" : "false");
      } else {
        const collapsed = body.classList.toggle("sidebar-collapsed");
        localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
        resToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      }
    });
    // Mobile: close drawer when tapping the scrim
    document.addEventListener("click", (e) => {
      if (!isMobile() || !body.classList.contains("show-resources")) return;
      const aside = document.getElementById("resources");
      if (e.target === resToggle || aside.contains(e.target)) return;
      body.classList.remove("show-resources");
      resToggle.setAttribute("aria-expanded", "false");
    });
  }

  window.addEventListener("resize", applySidebarState);
  applySidebarState();
}

boot();
