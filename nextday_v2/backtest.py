# -*- coding: utf-8 -*-
"""nextday_v2 回测模块
数据源: 每日流程的K线缓存(kline_cache.json, 每日自动更新) + 新浪真实上证指数
闸门 = 指数>MA10 且 宽度>=55% 且 涨停家数>8, 出信号次日持有, TopN等权
结果写入 data/v2/backtest_result.json, 页面/api/backtest读取

口径说明: 与bt_topn.py一致(walk-forward, 真实指数)。回测区间内滚动300日收益
从未跌破-10%, 熊市强制空仓条款未触发, 故此处不做重复判断。
"""
import datetime
import json
import os
import numpy as np

from . import config
from .datasource import fetch_index, DataError
from .engine import KLINE_CACHE, build_matrix, _nansort_desc

BT_FILE = os.path.join(config.DATA_DIR, "backtest_result.json")
TOPNS = [5, 10, 15, 20]


def _load_klines():
    try:
        with open(KLINE_CACHE, encoding="utf-8") as fp:
            c = json.load(fp)
    except Exception:
        raise DataError("K线缓存不存在, 请先运行一次每日流程")
    if not c.get("klines"):
        raise DataError("K线缓存为空, 请先运行一次每日流程")
    return c.get("date"), c["klines"]


def run_backtest():
    cache_date, klines = _load_klines()
    index_rows = fetch_index(config.INDEX_LEN)
    dates, codes, M = build_matrix(klines)
    n = len(dates)
    if n < config.MOM_WINDOW + 30:
        raise DataError(f"K线长度不足({n}根), 无法回测")

    # 宽度 / 涨停家数 / 指数MA (与engine同口径, 对齐t日)
    ret1 = np.zeros_like(M)
    ret1[1:] = M[1:] / M[:-1] - 1
    lim_th = np.array([0.195 if c[-6:].startswith(("30", "68")) else 0.095
                       for c in codes])
    is_zt = ret1 >= lim_th
    breadth = np.full(n, np.nan)
    zt_count = np.full(n, np.nan)
    for i in range(1, n):
        valid = ~np.isnan(M[i]) & ~np.isnan(M[i - 1])
        breadth[i] = np.nanmean(np.where(valid, M[i] > M[i - 1], np.nan))
        zt_count[i] = (valid & is_zt[i]).sum()
    ic_map = {d: c for d, c in index_rows}
    ic = np.array([ic_map.get(d, np.nan) for d in dates])
    for i in range(1, n):
        if np.isnan(ic[i]):
            ic[i] = ic[i - 1]
    with np.errstate(invalid="ignore"):
        ma = np.array([np.nanmean(ic[max(0, i - config.GATE_MA + 1):i + 1])
                       for i in range(n)])

    results = {k: [] for k in TOPNS}
    days = []
    start = max(60, config.MOM_WINDOW + 1)
    for t in range(start, n - 2):
        if np.isnan(breadth[t]) or np.isnan(zt_count[t]) or np.isnan(ic[t]):
            continue
        if not (ic[t] > ma[t] and breadth[t] >= config.BREADTH_TH
                and zt_count[t] > config.ZT_COUNT_TH):
            continue
        f = M[t] / M[t - config.MOM_WINDOW] - 1
        valid = ~np.isnan(f) & ~np.isnan(M[t + 1]) & ~np.isnan(M[t + 2])
        order = [j for j in _nansort_desc(np.where(valid, f, np.nan)) if valid[j]]
        day = {"date": dates[t], "zt_count": int(zt_count[t]),
               "breadth": round(float(breadth[t]), 4)}
        for k in TOPNS:
            idx = order[:k]
            r = float(np.nanmean(M[t + 2, idx] / M[t + 1, idx] - 1))
            results[k].append(round(r, 4))
            day[f"top{k}"] = round(r * 100, 2)
        days.append(day)

    topn_stats = {}
    for k in TOPNS:
        rs = np.array(results[k])
        if len(rs) == 0:
            continue
        topn_stats[str(k)] = {
            "win_rate": round(float((rs > 0).mean()), 4),
            "avg_ret": round(float(rs.mean()) * 100, 2),
            "cum_ret": round((float(np.prod(1 + rs)) - 1) * 100, 1),
            "worst": round(float(rs.min()) * 100, 2),
            "best": round(float(rs.max()) * 100, 2),
            "std": round(float(rs.std()) * 100, 2),
            "loss_days": int((rs <= 0).sum()),
        }
    out = {
        "run_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cache_date": cache_date,
        "data_range": [dates[start], dates[-1]],
        "gate": (f"指数>MA{config.GATE_MA} 且 宽度>={config.BREADTH_TH:.0%} "
                 f"且 涨停>{config.ZT_COUNT_TH}家"),
        "n_signals": len(days),
        "topn": topn_stats,
        "days": days,
    }
    with open(BT_FILE, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    return out


def load_result():
    if os.path.exists(BT_FILE):
        with open(BT_FILE, encoding="utf-8") as fp:
            return json.load(fp)
    return None
