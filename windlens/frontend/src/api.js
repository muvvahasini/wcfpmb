const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

export async function get(path, params = {}, signal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value != null) query.set(key, String(value));
  }
  const qs = query.toString();
  const endpoint = `${BASE}/api/${path.replace(/^\/+/, "")}${qs ? `?${qs}` : ""}`;
  const res = await fetch(endpoint, { signal });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  }
  return res.json();
}
