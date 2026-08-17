# -*- coding: utf-8 -*-
"""nextday_v2 策略引擎
回测依据(2025.4~2026.8, 全A流通市值前300, walk-forward):
  动量20日选股 + 指数MA20闸门 + 次日持有Top20:
  信号日189天, 胜率67%, 日均涨+0.76%, 累计+284% (等权基准+72%)
交易语义: t日收盘出信号 -> t+1日临近收盘买入 -> t+2日收盘卖出
"""
import datetime
import json
import os
import numpy as np
from . import config
from .datasource import fetch_pool, fetch_klines, fetch_index, DataError

KLINE_CACHE = os.path.join(config.DATA_DIR, "kline_cache.json")


def _load_cache():
    """当日K线缓存: {'date': 'YYYY-MM-DD', 'klines': {code: rows}}"""
    try:
        with open(KLINE_CACHE, encoding="utf-8") as fp:
            c = json.load(fp)
        return c if c.get("klines") else {"date": None, "klines": {}}
    except Exception:
        return {"date": None, "klines": {}}


def _save_cache(date, klines):
    with open(KLINE_CACHE, "w", encoding="utf-8") as fp:
        json.dump({"date": date, "klines": klines}, fp)


def _nansort_desc(arr):
    return np.argsort(np.where(np.isnan(arr), -np.inf, arr))[::-1]


def _limit_pct(code):
    """涨跌幅限制: 创业板30/科创68为20%, 其余主板10%"""
    num = code[-6:]
    return config.LIMIT_CYB if num.startswith(("30", "68")) else config.LIMIT_MAIN


def analyze_market(index_rows):
    """大盘闸门与市场状态
    返回 {'gate_open': bool, 'market_state': 'bull'/'bear'/'range',
          'index_date', 'index_close', 'ma20', 'ret_long'}
    """
    closes = np.array([r[1] for r in index_rows])
    dates = [r[0] for r in index_rows]
    ma = np.mean(closes[-config.GATE_MA:])
    ret_long = closes[-1] / closes[0] - 1  # 可用区间的累计涨幅(最多300日)
    if ret_long > config.BULL_TH:
        state = "bull"
    elif ret_long < config.BEAR_TH:
        state = "bear"
    else:
        state = "range"
    # 指数闸门(最终闸门还要叠加市场宽度, 见run_predict)
    index_gate = bool(closes[-1] > ma) and state != "bear"
    return {
        "gate_open": index_gate,
        "index_gate": index_gate,
        "market_state": state,
        "index_date": dates[-1],
        "index_close": float(closes[-1]),
        "ma_gate": float(ma),
        "ret_long": float(ret_long),
    }


def build_matrix(klines, min_len=config.MIN_KLINE):
    """{code: rows} -> (dates, codes, M收盘价矩阵)"""
    all_dates = sorted({r[0] for rows in klines.values() for r in rows})
    di = {d: i for i, d in enumerate(all_dates)}
    codes = [c for c, rows in klines.items() if len(rows) >= min_len]
    M = np.full((len(all_dates), len(codes)), np.nan)
    for j, c in enumerate(codes):
        for r in klines[c]:
            if r[0] in di:
                M[di[r[0]], j] = r[1]
    return all_dates, codes, M


def run_predict(pool_size=config.POOL_SIZE, topn=config.TOP_N):
    """完整预测流程 -> result dict (与老版格式兼容)"""
    pool = fetch_pool(pool_size)
    names = {c: nm for c, nm, _ in pool}
    ltsz = {c: sz for c, _, sz in pool}
    codes_all = [c for c, _, _ in pool]

    index_rows = fetch_index(config.INDEX_LEN)
    market = analyze_market(index_rows)

    # 当日K线缓存: 限流/重跑时兜底
    cache = _load_cache()
    cached = cache["klines"] if cache["date"] == market["index_date"] else {}
    todo = [c for c in codes_all if c not in cached]
    fresh = fetch_klines(todo, config.KLINE_LEN, min_len=config.MIN_KLINE) if todo else {}
    klines = {**cached, **fresh}
    if fresh:
        _save_cache(market["index_date"], {c: rows for c, rows in klines.items()})
    if len(klines) < 50:
        raise DataError(f"K线拉取过少: 仅{len(klines)}只")

    dates, codes, M = build_matrix(klines)
    t = len(dates) - 1
    if t < config.MOM_WINDOW:
        raise DataError("K线长度不足")
    trade_date = dates[t]

    # 市场宽度: 池内当日收涨家数占比 (防守闸门第二道)
    up = M[t] > M[t - 1]
    valid_mask = ~np.isnan(M[t]) & ~np.isnan(M[t - 1])
    breadth = float(np.nanmean(np.where(valid_mask, up, np.nan)))
    market["breadth"] = round(breadth, 4)
    market["breadth_th"] = config.BREADTH_TH
    gate_open = bool(market["index_gate"]) and breadth >= config.BREADTH_TH
    market["gate_open"] = gate_open
    if not market["index_gate"]:
        reason = ("熊市环境强制空仓" if market["market_state"] == "bear"
                  else f"指数{market['index_close']:.0f}跌破MA{config.GATE_MA}({market['ma_gate']:.0f})")
    elif not gate_open:
        reason = f"市场宽度不足: 上涨家数占比{breadth:.0%} < {config.BREADTH_TH:.0%}"
    else:
        reason = None

    preds = []
    if gate_open:
        mom = M[t] / M[t - config.MOM_WINDOW] - 1  # 动量因子
        order = _nansort_desc(mom)
        for rank, j in enumerate(order[:topn], 1):
            if np.isnan(mom[j]):
                continue
            code = codes[j]
            r1 = (M[t, j] / M[t - 1, j] - 1) * 100 if not np.isnan(M[t - 1, j]) else 0.0
            lim = _limit_pct(code)
            preds.append({
                "code": code,
                "name": names.get(code, ""),
                "rank": rank,
                "momentum20": round(float(mom[j]) * 100, 2),  # 20日动量%
                "r1": round(float(r1), 2),                    # 今日涨幅%
                "at_limit_up": bool(r1 >= lim - 0.5),          # 今日已涨停(次日追高风险)
                "ltsz": round(ltsz.get(code, 0), 1),           # 流通市值(亿)
            })

    return {
        "version": "v2",
        "strategy": (f"动量{config.MOM_WINDOW}日 + 防守闸门"
                     f"(指数MA{config.GATE_MA} + 宽度{config.BREADTH_TH:.0%})"),
        "trade_date": trade_date,
        "target_date": _next_weekday(trade_date),
        "buy_date": _next_weekday(trade_date),          # t+1临近收盘买入
        "sell_date": _next_weekday(_next_weekday(trade_date)),  # t+2收盘卖出
        "gate_open": gate_open,
        "market": market,
        "n_pool": len(codes_all),
        "n_kline_ok": len(klines),
        "predictions": preds,
        "gate_closed_reason": reason,
    }


def _next_weekday(date_str):
    d = datetime.date.fromisoformat(date_str)
    for _ in range(10):
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            return d.isoformat()
    return None
