// API封装
const base = "";

async function get(path) {
  const res = await fetch(base + path);
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} ${txt}`);
  }
  return res.json();
}

export const api = {
  overview: () => get("/api/overview"),
  winrate: () => get("/api/winrate"),
  dates: () => get("/api/predictions/dates"),
  predictions: (date) => get(`/api/predictions/${date}`),
  run: () => fetch(base + "/api/run", { method: "POST" }).then((r) => r.json()),
  runStatus: () => get("/api/run_status"),
};
