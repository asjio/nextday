# -*- coding: utf-8 -*-
"""每日流程编排: 选候选池 -> 拉K线 -> 建模 -> 预测 -> 存档"""
import json
import random
from concurrent.futures import ThreadPoolExecutor
from . import config
from .datasource import snapshot, kline
from .model import NextDayModel


def _num(r, k):
    try:
        return float(r.get(k) or 0)
    except Exception:
        return 0.0


def pick_universe(snap):
    """选样本池: 资金强度top N + 显式跟踪 + 随机对照"""
    cand = []
    for code, r in snap.items():
        num = code[-6:]
        name = r.get("name", "")
        if "ST" in name or "退" in name:
            continue
        if num.startswith(config.EXCLUDE_PREFIX):
            continue
        if _num(r, "zxj") < config.MIN_PRICE:
            continue
        if _num(r, "ltsz") < config.MIN_LTSZ:
            continue
        r = dict(r)
        r["qiangdu"] = _num(r, "zljlr") / max(_num(r, "ltsz"), 1)
        cand.append(r)
    cand.sort(key=lambda r: r["qiangdu"], reverse=True)
    picks = cand[:config.TOP_N_BY_STRENGTH]
    picked = {r["code"] for r in picks}
    for c in config.TRACK_CODES:
        if c in snap and c not in picked:
            picks.append(snap[c])
            picked.add(c)
    # 只要求收涨+主力净流入(预测目标日前提)
    picks = [r for r in picks
             if _num(r, "zdf") > 0 and _num(r, "zljlr") > 0]
    random.seed(42)
    pool = [r for r in snap.values() if r["code"] not in picked
            and "ST" not in r.get("name", "") and _num(r, "zxj") > 2]
    rnd = random.sample(pool, min(config.RANDOM_N, len(pool)))
    return picks + rnd


def fetch_klines(codes, n=config.KLINE_LEN, workers=12):
    """并行拉K线 -> {code: rows}"""
    out = {}

    def one(code):
        for _ in range(3):
            try:
                rows = kline(code, n)
                if len(rows) > 80:
                    return code, rows
            except Exception:
                pass
        return code, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for code, rows in ex.map(one, codes):
            if rows:
                out[code] = rows
    return out


def run_predict():
    """完整预测流程, 返回 {'trade_date', 'baseline', 'n_samples', 'predictions'}"""
    snap = snapshot()
    universe = pick_universe(snap)
    names = {r["code"]: r["name"] for r in universe}
    klines = fetch_klines([r["code"] for r in universe])
    kline_dict = {c: {"name": names.get(c, ""), "rows": rows} for c, rows in klines.items()}
    model = NextDayModel().build(kline_dict)
    preds = model.predict_all()
    trade_date = preds[0]["date"] if preds else ""
    return {
        "trade_date": trade_date,
        "baseline": round(model.baseline, 4),
        "n_samples": model.n_samples,
        "n_universe": len(universe),
        "n_kline_ok": len(klines),
        "predictions": preds,
    }
