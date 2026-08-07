# -*- coding: utf-8 -*-
"""验证模块: 次日收盘后对账 + 胜率历史累积"""
import json
import os
from . import config
from .datasource import kline, is_trading_day

WINRATE_FILE = os.path.join(config.DATA_DIR, "winrate_history.json")
PRED_DIR = config.PRED_DIR


def _pct(c1, c0):
    return (c1 / c0 - 1) * 100


def next_trading_close(kline_rows, base_date):
    """返回base_date之后第一个交易日的(date, close), 没有则None"""
    after = [r for r in kline_rows if r[0] > base_date]
    if not after:
        return None
    r = after[0]
    return r[0], float(r[2])


def validate_one(pred_file):
    """对账一个预测文件。pred: {'trade_date', 'predictions': [...]}
    返回 {'done': bool, 'record': 胜率记录 or None}"""
    with open(pred_file, encoding="utf-8") as fp:
        pred = json.load(fp)
    trade_date = pred["trade_date"]
    preds = pred["predictions"]
    if not preds:
        return {"done": True, "record": None}

    results = []
    missing = 0
    for p in preds:
        try:
            rows = kline(p["code"], 40)
        except Exception:
            missing += 1
            continue
        closes = {r[0]: float(r[2]) for r in rows}
        c0 = closes.get(trade_date)
        nxt = next_trading_close(rows, trade_date)
        if c0 is None or nxt is None:
            missing += 1
            continue
        actual = _pct(nxt[1], c0)
        results.append({
            "code": p["code"], "name": p["name"],
            "p_up": p["p_up"], "actual": round(actual, 2),
            "hit": actual > 0, "next_date": nxt[0],
        })
    if missing > len(preds) * 0.5:
        # 次日还没收盘, 不能对账
        return {"done": False, "record": None}
    if not results:
        return {"done": False, "record": None}

    next_date = results[0]["next_date"]
    n = len(results)
    hit = sum(r["hit"] for r in results)
    top12 = sorted(results, key=lambda r: -r["p_up"])[:12]
    hc = [r for r in results if r["p_up"] >= 0.70]
    record = {
        "pred_date": trade_date,
        "target_date": next_date,
        "n": n,
        "hit_rate": round(hit / n, 4),
        "avg_actual": round(sum(r["actual"] for r in results) / n, 3),
        "top12_hit_rate": round(sum(r["hit"] for r in top12) / len(top12), 4),
        "top12_avg": round(sum(r["actual"] for r in top12) / len(top12), 3),
        "high_conf_n": len(hc),
        "high_conf_hit_rate": round(sum(r["hit"] for r in hc) / len(hc), 4) if hc else None,
        "high_conf_avg": round(sum(r["actual"] for r in hc) / len(hc), 3) if hc else None,
        "top5": [
            {"code": r["code"][-6:], "name": r["name"],
             "p_up": round(r["p_up"], 3), "actual": r["actual"]}
            for r in top12[:5]
        ],
    }
    return {"done": True, "record": record, "detail": results}


def load_history():
    if os.path.exists(WINRATE_FILE):
        with open(WINRATE_FILE, encoding="utf-8") as fp:
            return json.load(fp)
    return []


def save_history(records):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    records.sort(key=lambda r: r["pred_date"])
    with open(WINRATE_FILE, "w", encoding="utf-8") as fp:
        json.dump(records, fp, ensure_ascii=False, indent=1)


def validate_all():
    """扫描所有未对账的预测文件, 对账并累积胜率记录。返回新增记录列表。"""
    if not os.path.isdir(PRED_DIR):
        return []
    history = load_history()
    done_dates = {r["pred_date"] for r in history}
    added = []
    for fn in sorted(os.listdir(PRED_DIR)):
        if not fn.startswith("pred_") or not fn.endswith(".json"):
            continue
        path = os.path.join(PRED_DIR, fn)
        res = validate_one(path)
        if res["done"] and res["record"]:
            rec = res["record"]
            if rec["pred_date"] not in done_dates:
                history.append(rec)
                added.append(rec)
                # 明细另存
                detail_path = path.replace("pred_", "detail_")
                with open(detail_path, "w", encoding="utf-8") as fp:
                    json.dump(res["detail"], fp, ensure_ascii=False, indent=1)
    if added:
        save_history(history)
    return added
