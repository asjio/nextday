// GitHub Pages 静态模式 - 从相对路径读取数据
const BASE = "./data";

export const api = {
  overview: async () => {
    const res = await fetch(`${BASE}/winrate_history.json`);
    if (!res.ok) throw new Error("无法加载胜率数据");
    const history = await res.json();
    const latest = history[history.length - 1];
    const totalSamples = history.reduce((sum, d) => sum + d.total_samples, 0);
    return {
      total_days: history.length,
      total_samples: totalSamples,
      latest_date: latest.date,
      win_rate_all: latest.win_rate_all,
      win_rate_top12: latest.win_rate_top12,
      win_rate_high_conf: latest.win_rate_high_conf,
      avg_return: latest.avg_return
    };
  },
  
  winrate: async () => {
    const res = await fetch(`${BASE}/winrate_history.json`);
    if (!res.ok) throw new Error("无法加载胜率数据");
    return res.json();
  },
  
  dates: async () => {
    // 从 manifest 读取可用日期
    const res = await fetch(`${BASE}/predictions/manifest.json`);
    if (!res.ok) return [];
    const manifest = await res.json();
    return manifest.dates || [];
  },
  
  predictions: async (date) => {
    const res = await fetch(`${BASE}/predictions/${date}.json`);
    if (!res.ok) throw new Error(`无法加载 ${date} 的预测数据`);
    return res.json();
  },
  
  // 静态模式不支持手动执行
  run: async () => {
    throw new Error("GitHub Pages 静态模式不支持手动执行，请等待每日定时任务");
  },
  
  runStatus: async () => {
    return { running: false, last_done: null, error: null };
  }
};
