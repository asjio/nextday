// GitHub Pages 静态模式 - 从仓库 raw 文件读取数据
const RAW_BASE = "https://raw.githubusercontent.com/asjio/nextday/master/data";

export const api = {
  overview: async () => {
    const res = await fetch(`${RAW_BASE}/winrate_history.json`);
    if (!res.ok) return { days: 0, total_n: 0, summary: { hit_rate_all: 0, hit_rate_top12: 0, hit_rate_high_conf: null, avg_actual: 0 }, recent: [] };
    const history = await res.json();
    if (!history.length) return { days: 0, total_n: 0, summary: { hit_rate_all: 0, hit_rate_top12: 0, hit_rate_high_conf: null, avg_actual: 0 }, recent: [] };
    const latest = history[history.length - 1];
    const totalSamples = history.reduce((sum, d) => sum + (d.total_samples || 0), 0);
    return {
      days: history.length,
      total_n: totalSamples,
      summary: {
        hit_rate_all: latest.hit_rate_all != null ? latest.hit_rate_all : latest.hit_rate,
        hit_rate_top12: latest.top12_hit_rate,
        hit_rate_high_conf: latest.high_conf_hit_rate != null ? latest.high_conf_hit_rate : null,
        avg_actual: latest.avg_actual,
        baseline: 49.2
      },
      recent: history.slice().reverse().slice(0, 10)
    };
  },
  
  winrate: async () => {
    const res = await fetch(`${RAW_BASE}/winrate_history.json`);
    if (!res.ok) return { records: [] };
    const history = await res.json();
    const records = history.sort((a, b) => (a.pred_date || "").localeCompare(b.pred_date || ""));
    return { records };
  },
  
  dates: async () => {
    const res = await fetch(`${RAW_BASE}/predictions/manifest.json`);
    if (!res.ok) return { dates: [], validated: {} };
    const manifest = await res.json();
    return { dates: manifest.dates || [], validated: manifest.validated || {} };
  },
  
  predictions: async (date) => {
    const res = await fetch(`${RAW_BASE}/predictions/pred_${date}.json`);
    if (!res.ok) throw new Error(`无法加载 ${date} 的预测数据`);
    const raw = await res.json();
    // 转换为 App.jsx 期望的结构
    return {
      date: raw.trade_date || raw.date,
      target_date: raw.target_date || null,
      n_samples: raw.n_samples,
      baseline: raw.baseline,
      validated: raw.validated || false,
      items: (raw.predictions || []).map(p => ({
        code: (p.code || "").slice(-6),
        name: p.name,
        p_up: Math.round((p.p_up || 0) * 1000) / 10,
        p_up5: p.p_up5 != null ? Math.round(p.p_up5 * 1000) / 10 : null,
        p_down5: Math.round((p.p_down5 || 0) * 1000) / 10,
        median: p.median,
        r1: p.r1 || 0,
        actual: p.actual != null ? p.actual : null,
        hit: p.hit != null ? p.hit : null,
      }))
    };
  },
  
  run: async () => {
    throw new Error("GitHub Pages 静态模式不支持手动执行");
  },
  
  runStatus: async () => {
    return { running: false, last_done: null, error: null, log: [] };
  }
};
