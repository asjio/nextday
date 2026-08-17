# -*- coding: utf-8 -*-
"""nextday_v2 对账模块
信号语义: t日出信号, t+1收盘买入, t+2收盘卖出
对账条件: t+2收盘后(即sell_date当天收盘后运行)
"""
import json
import os
from . import config
from .datasource import fetch_kline, DataError


def load_history():
    if os.path.exists(config.WINRATE_FILE):
        with open(config.WINRATE_FILE, encoding="utf-8") as fp:
            return json.load(fp)
    return []


def save_history(records):
    records.sort(key=lambda r: r["pred_date"])
    with open(config.WINRATE_FILE, "w", encoding="utf-8") as fp:
        json.dump(records, fp, ensure_ascii=False, indent=1)


def calibrated_stats(history):
    """实测校准: 对账满CALIBRATE_MIN_DAYS天后用实测胜率/均涨替换回测值"""
    done = [r for r in history if r.get("gate_open", True) and r["n"] > 0]
    if len(done) < config.CALIBRATE_MIN_DAYS:
        return {"winrate": config.BT_WINRATE, "avg_ret": config.BT_AVG_RET,
                "calibrated": False, "n_days": len(done)}
    win = sum(r["hit_rate"] * r["n"] for r in done) / sum(r["n"] for r in done)
    avg = sum(r["avg_actual"] for r in done) / len(done)
    return {"winrate": round(win, 4), "avg_ret": round(avg, 3),
            "calibrated": True, "n_days": len(done)}


def validate_one(pred_file):
    """对账一个v2预测文件。闸门关闭日无需对账。"""
    with open(pred_file, encoding="utf-8") as fp:
        pred = json.load(fp)
    if pred.get("version") != "v2":
        return {"done": True, "record": None}
    trade_date = pred["trade_date"]
    preds = pred["predictions"]
    if not pred.get("gate_open", True):
        # 闸门关闭日: 空仓, 记一条n=0的记录便于统计空仓天数
        return {"done": True, "record": {
            "pred_date": trade_date, "target_date": pred.get("sell_date"),
            "gate_open": False, "n": 0, "hit_rate": None, "avg_actual": None,
        }}
    if not preds:
        return {"done": True, "record": None}

    results, missing = [], 0
    for p in preds:
        try:
            rows = fetch_kline(p["code"], 40)
        except Exception:
            missing += 1
            continue
        closes = {r[0]: r[1] for r in rows}
        after = sorted(d for d in closes if d > trade_date)
        # t+1收盘买入, t+2收盘卖出
        if len(after) < 2:
            missing += 1
            continue
        c_buy, c_sell = closes[after[0]], closes[after[1]]
        actual = (c_sell / c_buy - 1) * 100
        results.append({
            "code": p["code"], "name": p["name"], "rank": p["rank"],
            "momentum20": p["momentum20"], "r1": p["r1"],
            "buy_date": after[0], "sell_date": after[1],
            "actual": round(actual, 2), "hit": actual > 0,
        })
    if missing > len(preds) * 0.5 or not results:
        return {"done": False, "record": None}  # t+2还没收盘

    n = len(results)
    hit = sum(r["hit"] for r in results)
    top12 = sorted(results, key=lambda r: r["rank"])[:12]
    record = {
        "pred_date": trade_date,
        "target_date": results[0]["sell_date"],
        "gate_open": True,
        "market_state": pred.get("market", {}).get("market_state"),
        "n": n,
        "hit_rate": round(hit / n, 4),
        "avg_actual": round(sum(r["actual"] for r in results) / n, 3),
        "top12_hit_rate": round(sum(r["hit"] for r in top12) / len(top12), 4),
        "top12_avg": round(sum(r["actual"] for r in top12) / len(top12), 3),
        "top5": [{"code": r["code"][-6:], "name": r["name"],
                  "momentum20": r["momentum20"], "actual": r["actual"]}
                 for r in top12[:5]],
    }
    return {"done": True, "record": record, "detail": results}


def validate_all():
    """扫描未对账的v2预测文件, 返回新增记录列表"""
    if not os.path.isdir(config.PRED_DIR):
        return []
    history = load_history()
    done_dates = {r["pred_date"] for r in history}
    added = []
    for fn in sorted(os.listdir(config.PRED_DIR)):
        if not fn.startswith("pred_") or not fn.endswith(".json"):
            continue
        path = os.path.join(config.PRED_DIR, fn)
        res = validate_one(path)
        if res["done"] and res["record"]:
            rec = res["record"]
            if rec["pred_date"] in done_dates:
                continue
            history.append(rec)
            added.append(rec)
            detail_path = path.replace("pred_", "detail_")
            with open(detail_path, "w", encoding="utf-8") as fp:
                json.dump(res.get("detail", []), fp, ensure_ascii=False, indent=1)
            if res.get("detail"):
                detail_map = {d["code"]: d for d in res["detail"]}
                with open(path, encoding="utf-8") as fp:
                    pred = json.load(fp)
                for p in pred["predictions"]:
                    d = detail_map.get(p["code"])
                    if d:
                        p["actual"] = d["actual"]
                        p["hit"] = d["hit"]
                pred["validated"] = True
                with open(path, "w", encoding="utf-8") as fp:
                    json.dump(pred, fp, ensure_ascii=False, indent=1)
    if added:
        save_history(history)
    return added
