const TOKEN_KEY = "dashboard_token";
localStorage.removeItem(TOKEN_KEY);

export function getToken() { return ""; }

export async function login(token) {
  const r = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ token }),
  });
  if (!r.ok) throw new Error(`login -> ${r.status}`);
  return r.json();
}

export async function sessionActive() {
  const r = await fetch("/api/session", { credentials: "same-origin" });
  return r.ok;
}

export async function logout() {
  await fetch("/api/session", { method: "DELETE", credentials: "same-origin" });
}

async function req(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const r = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 204) return null;
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}`);
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

export const api = {
  list: (qs="") => req("GET", `/api/items${qs}`),
  get:  (id) => req("GET", `/api/items/${id}`),
  create: (item) => req("POST", "/api/items", item),
  update: (id, fields) => req("PATCH", `/api/items/${id}`, fields),
  remove: (id) => req("DELETE", `/api/items/${id}`),
  complete: (id) => req("POST", `/api/items/${id}/complete`),
  system: () => req("GET", "/api/system"),
  services: () => req("GET", "/api/services"),
};
