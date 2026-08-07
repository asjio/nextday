// GitHub Pages 静态模式 - 从仓库 raw 文件读取数据
const RAW_BASE = "https://raw.githubusercontent.com/asjio/nextday/master/data";

export const api = {
  overview: async () => {
    const res = await fetch(`${RAW_BASE}/winrate_history.json`);
    if (!res.ok) throw new Error("无法加载胜率数据");
    const history = await res.json();
    const latest = history[history.length - 1];
    const totalSamples = history.reduce((sum, d) => sum + (d.total_samples || 0), 0);
    return {
      total_days: history.length,
      total_samples: totalSamples,
      latest_date: latest.date || latest.pred_date,
      win_rate_all: (latest.hit_rate_all || latest.hit_rate || 0) * 100,
      win_rate_top12: (latest.top12_hit_rate || 0) * 100,
      win_rate_high_conf: latest.high_conf_hit_rate != null ? latest.high_conf_hit_rate * 100 : null,
      avg_return: latest.avg_actual || 0
    };
  },
  
  winrate: async () => {
    const res = await fetch(`${RAW_BASE}/winrate_history.json`);
    if (!res.ok) throw new Error("无法加载胜率数据");
    return res.json();
  },
  
  dates: async () => {
    const res = await fetch(`${RAW_BASE}/predictions/manifest.json`);
    if (!res.ok) return [];
    const manifest = await res.json();
    return manifest.dates || [];
  },
  
  predictions: async (date) => {
    const res = await fetch(`${RAW_BASE}/predictions/pred_${date}.json`);
    if (!res.ok) throw new Error(`无法加载 ${date} 的预测数据`);
    return res.json();
  },
  
  run: async () => {
    throw new Error("GitHub Pages 静态模式不支持手动执行，请等待每日定时任务");
  },
  
  runStatus: async () => {
    return { running: false, last_done: null, error: null };
  }
};
