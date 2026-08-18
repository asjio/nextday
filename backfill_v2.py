# -*- coding: utf-8 -*-
"""回填v2历史对账记录: 用当日拉取的K线缓存walk-forward回放
说明: 股票池为"今日"流通市值前300(轻微幸存者偏差, 近几日可忽略)
信号语义与engine一致: t日收盘动量20日Top20, t+1收盘买, t+2收盘卖
闸门与engine一致: 指数>MA20 且 非熊市
"""
import json
import os
import numpy as np
from nextday_v2 import config
from nextday_v2.datasource import fetch_index, fetch_pool

N_SIGNAL_DAYS = 70  # 回填最近N个可完整对账的信号日(覆盖约3.5个月, 拿到足够开仓样本)


def nansort_desc(arr):
    return np.argsort(np.where(np.isnan(arr), -np.inf, arr))[::-1]


def main():
    cache_path = os.path.join(config.DATA_DIR, "kline_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8"))
    klines = {k: v for k, v in cache["klines"].items() if v and len(v) >= config.MIN_KLINE}
    print(f"缓存股票: {len(klines)}只", flush=True)

    # 盘中保护: 15:05前运行时剥离今天未收盘的数据(宽度/涨停家数按残缺数据算会失真)
    import datetime as _dt
    today = _dt.date.today().isoformat()
    if _dt.datetime.now().strftime("%H%M") < "1505":
        klines = {c: [r for r in rows if r[0] != today] for c, rows in klines.items()}
        print("盘中运行: 已剥离今日未收盘数据", flush=True)

    pool = fetch_pool(config.POOL_SIZE)
    names = {c: nm for c, nm, _ in pool}
    ltsz = {c: sz for c, _, sz in pool}

    index_rows = fetch_index(config.INDEX_LEN)
    idx_close = {d: c for d, c in index_rows}

    all_dates = sorted({r[0] for rows in klines.values() for r in rows})
    di = {d: i for i, d in enumerate(all_dates)}
    codes = list(klines.keys())
    n = len(all_dates)
    M = np.full((n, len(codes)), np.nan)
    for j, c in enumerate(codes):
        for r in klines[c]:
            if r[0] in di:
                M[di[r[0]], j] = r[1]

    # 信号日窗口: 含最后2个未到卖出日的日期(空仓记录无需对账, UI要展示完整周)
    max_t = n - 1
    signal_days = list(range(max(60, max_t - N_SIGNAL_DAYS + 1), max_t + 1))
    print(f"回填信号日: {all_dates[signal_days[0]]} ~ {all_dates[signal_days[-1]]} ({len(signal_days)}天)", flush=True)

    # 指数序列对齐到交易日轴
    ic = np.array([idx_close.get(d, np.nan) for d in all_dates])
    for i in range(1, n):
        if np.isnan(ic[i]):
            ic[i] = ic[i - 1]
    # 市场宽度 + 涨停家数: 与engine一致口径
    breadth = np.full(n, np.nan)
    zt_count = np.full(n, np.nan)
    lim_th = np.array([0.195 if c[-6:].startswith(("30", "68")) else 0.095
                       for c in codes])
    for i in range(1, n):
        valid = ~np.isnan(M[i]) & ~np.isnan(M[i - 1])
        breadth[i] = np.nanmean(np.where(valid, M[i] > M[i - 1], np.nan))
        r1i = M[i] / M[i - 1] - 1
        zt_count[i] = int((valid & (r1i >= lim_th)).sum())

    records = []
    for t in signal_days:
        td = all_dates[t]
        # 闸门: 指数>MA10 且 非熊市 且 宽度>=55% 且 涨停家数>8 (复合情绪)
        ma = np.mean(ic[t - config.GATE_MA + 1:t + 1])
        ret_long = ic[t] / ic[0] - 1
        if ret_long > config.BULL_TH:
            state = "bull"
        elif ret_long < config.BEAR_TH:
            state = "bear"
        else:
            state = "range"
        idx_gate = bool(ic[t] > ma) and state != "bear"
        gate_open = (idx_gate and float(breadth[t]) >= config.BREADTH_TH
                     and zt_count[t] > config.ZT_COUNT_TH)

        pred_path = os.path.join(config.PRED_DIR, f"pred_{td}.json")
        detail_path = os.path.join(config.PRED_DIR, f"detail_{td}.json")

        # 已存在的实盘预测(非回填生成)不覆盖
        if os.path.exists(pred_path):
            try:
                old = json.load(open(pred_path, encoding="utf-8"))
                if not old.get("backfilled"):
                    print(f"  {td}: 实盘预测已存在, 跳过", flush=True)
                    continue
            except Exception:
                pass

        if not gate_open:
            if state == "bear":
                reason = "熊市环境强制空仓"
            elif not idx_gate:
                reason = f"指数{ic[t]:.0f}跌破MA{config.GATE_MA}({ma:.0f})"
            elif float(breadth[t]) < config.BREADTH_TH:
                reason = f"市场宽度不足: 上涨占比{float(breadth[t]):.0%} < {config.BREADTH_TH:.0%}"
            else:
                reason = f"资金进攻不足: 池内涨停{int(zt_count[t])}家 <= {config.ZT_COUNT_TH}家"
            rec = {"pred_date": td, "target_date": all_dates[t + 2] if t + 2 < n else None,
                   "gate_open": False, "n": 0, "hit_rate": None, "avg_actual": None}
            records.append(rec)
            pred = {"version": "v2", "backfilled": True, "trade_date": td,
                    "gate_open": False,
                    "gate_closed_reason": reason,
                    "market": {"market_state": state, "index_close": float(ic[t]),
                               "ma_gate": float(ma), "breadth": float(breadth[t]),
                               "breadth_th": config.BREADTH_TH,
                               "zt_count": int(zt_count[t]), "zt_count_th": config.ZT_COUNT_TH},
                    "buy_date": all_dates[t + 1] if t + 1 < n else None,
                    "sell_date": all_dates[t + 2] if t + 2 < n else None,
                    "predictions": []}
            json.dump(pred, open(pred_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  {td}: 闸门关({reason}) -> 空仓", flush=True)
            continue

        # 开仓日: 必须能完整对账(卖出日已过), 否则跳过等对账
        if t + 2 >= n:
            print(f"  {td}: 闸门开但卖出日未到, 跳过(待对账)", flush=True)
            continue

        mom = M[t] / M[t - config.MOM_WINDOW] - 1
        order = nansort_desc(mom)
        top_idx = [j for j in order[:config.TOP_N] if not np.isnan(mom[j])]

        preds, detail, results = [], [], []
        for rank, j in enumerate(top_idx, 1):
            code = codes[j]
            c_buy, c_sell = M[t + 1, j], M[t + 2, j]
            if np.isnan(c_buy) or np.isnan(c_sell):
                continue
            actual = (c_sell / c_buy - 1) * 100
            r1 = (M[t, j] / M[t - 1, j] - 1) * 100 if not np.isnan(M[t - 1, j]) else 0.0
            num = code[-6:]
            lim = config.LIMIT_CYB if num.startswith(("30", "68")) else config.LIMIT_MAIN
            p = {"code": code, "name": names.get(code, code), "rank": rank,
                 "momentum20": round(float(mom[j]) * 100, 2),
                 "r1": round(float(r1), 2),
                 "at_limit_up": bool(r1 >= lim - 0.5),
                 "ltsz": round(ltsz.get(code, 0), 1),
                 "actual": round(float(actual), 2), "hit": bool(actual > 0)}
            preds.append(p)
            detail.append({**p, "buy_date": all_dates[t + 1], "sell_date": all_dates[t + 2]})
            results.append(actual)

        hit = sum(1 for r in results if r > 0)
        top12 = [p for p in preds[:12]]
        rec = {
            "pred_date": td, "target_date": all_dates[t + 2],
            "gate_open": True, "market_state": state, "n": len(results),
            "hit_rate": round(hit / len(results), 4),
            "avg_actual": round(sum(results) / len(results), 3),
            "top12_hit_rate": round(sum(1 for p in top12 if p["hit"]) / len(top12), 4),
            "top12_avg": round(sum(p["actual"] for p in top12) / len(top12), 3),
            "top5": [{"code": p["code"][-6:], "name": p["name"],
                      "momentum20": p["momentum20"], "actual": p["actual"]}
                     for p in top12[:5]],
        }
        records.append(rec)
        pred = {"version": "v2", "backfilled": True, "trade_date": td,
                "strategy": (f"动量{config.MOM_WINDOW}日 + 复合情绪闸门"
                             f"(指数MA{config.GATE_MA} + 宽度{config.BREADTH_TH:.0%} + 涨停>{config.ZT_COUNT_TH}家)"),
                "gate_open": True, "market": {"market_state": state,
                "index_close": float(ic[t]), "ma_gate": float(ma),
                "breadth": float(breadth[t]), "breadth_th": config.BREADTH_TH,
                "zt_count": int(zt_count[t]), "zt_count_th": config.ZT_COUNT_TH},
                "buy_date": all_dates[t + 1], "sell_date": all_dates[t + 2],
                "validated": True, "predictions": preds}
        json.dump(pred, open(pred_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(detail, open(detail_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  {td}: 命中{rec['hit_rate']*100:.0f}% Top12命中{rec['top12_hit_rate']*100:.0f}% "
              f"均涨{rec['avg_actual']:+.2f}% Top12均涨{rec['top12_avg']:+.2f}%", flush=True)

    # 合并写入winrate_history(保留已有非回填记录)
    hist_path = config.WINRATE_FILE
    existing = []
    if os.path.exists(hist_path):
        existing = json.load(open(hist_path, encoding="utf-8"))
    old_dates = {r["pred_date"] for r in existing}
    for r in records:
        if r["pred_date"] not in old_dates:
            existing.append(r)
    existing.sort(key=lambda r: r["pred_date"])
    json.dump(existing, open(hist_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    open_days = [r for r in records if r.get("gate_open") and r.get("n")]
    if open_days:
        tot_n = sum(r["n"] for r in open_days)
        w = sum(r["hit_rate"] * r["n"] for r in open_days) / tot_n * 100
        avg = sum(r["avg_actual"] for r in open_days) / len(open_days)
        print(f"\n回填完成: {len(records)}条记录 -> {hist_path}")
        print(f"开仓{len(open_days)}天: 加权命中率{w:.1f}% 日均涨{avg:+.2f}%")


if __name__ == "__main__":
    main()
