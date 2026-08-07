// GitHub Pages 静态模式 - 从仓库 raw 文件读取数据
const RAW_BASE = "https://raw.githubusercontent.com/asjio/nextday/master/data";

export const api = {
  overview: async () => {
    const res = await fetch(`${RAW_BASE}/winrate_history.json`);
    if (!res.ok) return { days: 0, total_n: 0, summary: { hit_rate_all: 0, hit_rate_top12: 0, hit_rate_high_conf: null, avg_actual: 0 }, recent: [] };
    const history = await res.json();
    if (!history.length) return { days: 0, total_n: 0, summary: { hit_rate_all: 0, hit_rate_top12: 0, hit_rate_high_conf: null, avg_actual: 0 }, recent: [] };
    
    // 累计统计: 加权平均
    let totalN = 0, totalHits = 0, totalT12Hits = 0, t12Count = 0;
    let totalHcHits = 0, hcCount = 0;
    let totalReturn = 0;
    
    for (const rec of history) {
      const n = rec.n || 0;
      totalN += n;
      totalHits += (rec.hit_rate || 0) * n;
      
      if (rec.top12_hit_rate != null) {
        totalT12Hits += rec.top12_hit_rate * 12;
        t12Count += 12;
      }
      if (rec.high_conf_hit_rate != null && rec.high_conf_n) {
        totalHcHits += rec.high_conf_hit_rate * rec.high_conf_n;
        hcCount += rec.high_conf_n;
      }
      totalReturn += (rec.avg_actual || 0) * n;
    }
    
    const hitAll = totalN > 0 ? (totalHits / totalN) * 100 : 0;
    const hitTop12 = t12Count > 0 ? (totalT12Hits / t12Count) * 100 : 0;
    const hitHc = hcCount > 0 ? (totalHcHits / hcCount) * 100 : null;
    const avgRet = totalN > 0 ? totalReturn / totalN : 0;
    
    return {
      days: history.length,
      total_n: totalN,
      summary: {
        hit_rate_all: Math.round(hitAll * 10) / 10,
        hit_rate_top12: Math.round(hitTop12 * 10) / 10,
        hit_rate_high_conf: hitHc != null ? Math.round(hitHc * 10) / 10 : null,
        avg_actual: Math.round(avgRet * 100) / 100,
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
  
  predictions: async (date, validatedMap = {}) => {
    const res = await fetch(`${RAW_BASE}/predictions/pred_${date}.json`);
    if (!res.ok) throw new Error(`无法加载 ${date} 的预测数据`);
    const raw = await res.json();
    // 优先用manifest的validated状态，再fallback到pred文件自身的validated字段
    const isValidated = validatedMap[date] || raw.validated || false;
    return {
      date: raw.trade_date || raw.date,
      target_date: raw.target_date || null,
      n_samples: raw.n_samples,
      baseline: raw.baseline,
      validated: isValidated,
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
  
  // 对账明细(用于计算当日命中率)
  detail: async (date) => {
    const res = await fetch(`${RAW_BASE}/predictions/detail_${date}.json`);
    if (!res.ok) return null;
    return res.json();
  },
  
  run: async () => {
    throw new Error("GitHub Pages 静态模式不支持手动执行");
  },
  
  runStatus: async () => {
    return { running: false, last_done: null, error: null, log: [] };
  }
};
