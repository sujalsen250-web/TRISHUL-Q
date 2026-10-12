// Thin API client. Cookie sessions (same-origin), JSON bodies.
export async function api(path, opts = {}) {
  const cfg = { credentials: "same-origin", headers: {}, ...opts };
  if (cfg.body && !(cfg.body instanceof FormData)) {
    cfg.headers["Content-Type"] = "application/json";
    cfg.body = JSON.stringify(cfg.body);
  }
  const res = await fetch(path, cfg);
  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }
  if (!res.ok) {
    const msg = data && data.detail ? data.detail : `Request failed (${res.status})`;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const get = (p) => api(p);
export const post = (p, body) => api(p, { method: "POST", body });
export const put = (p, body) => api(p, { method: "PUT", body });

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function fmtTime(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
}

export function shortHash(h, n = 16) {
  if (!h) return "—";
  return h.length > n ? h.slice(0, n) + "…" : h;
}
