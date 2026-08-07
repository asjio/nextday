# -*- coding: utf-8 -*-
"""NextDay Web服务: FastAPI + 静态前端
启动: python -m nextday.web  (或双击 web.bat)
端口: 8766
"""
import json
import os
import threading
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .validate import load_history
from .datasource import next_trading_date, DataError

PORT = 8766
app = FastAPI(title="NextDay")

# ---- 后台运行状态 ----
_run_state = {"running": False, "log": [], "last_done": None, "error": None}


def _read_pred(date_str):
    path = os.path.join(config.PRED_DIR, f"pred_{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def _read_detail(date_str):
    path = os.path.join(config.PRED_DIR, f"detail_{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def _list_dates():
    dates = []
    if os.path.isdir(config.PRED_DIR):
        for fn in sorted(os.listdir(config.PRED_DIR)):
            if fn.startswith("pred_") and fn.endswith(".json"):
                dates.append(fn[5:-5])
    return sorted(dates, reverse=True)


@app.get("/api/overview")
def overview():
    """累计统计 + 最近记录"""
    records = load_history()
    if not records:
        return {"days": 0, "total_n": 0, "summary": {}, "recent": []}
    tot_n = sum(r["n"] for r in records)
    w_all = sum(r["hit_rate"] * r["n"] for r in records) / tot_n * 100
    t12 = sum(r["top12_hit_rate"] for r in records) / len(records) * 100
    hc = [r for r in records if r.get("high_conf_hit_rate") is not None]
    w_hc = sum(r["high_conf_hit_rate"] for r in hc) / len(hc) * 100 if hc else None
    avg_all = sum(r["avg_actual"] for r in records) / len(records)
    return {
        "days": len(records),
        "total_n": tot_n,
        "summary": {
            "hit_rate_all": round(w_all, 1),
            "hit_rate_top12": round(t12, 1),
            "hit_rate_high_conf": round(w_hc, 1) if w_hc is not None else None,
            "avg_actual": round(avg_all, 2),
            "baseline": 49.2,
        },
        "recent": sorted(records, key=lambda r: r["pred_date"], reverse=True)[:10],
    }


@app.get("/api/winrate")
def winrate():
    """胜率曲线数据"""
    records = load_history()
    records.sort(key=lambda r: r["pred_date"])
    return {"records": records}


@app.get("/api/predictions/dates")
def pred_dates():
    return {"dates": _list_dates(), "validated": {r["pred_date"]: True for r in load_history()}}


@app.get("/api/predictions/{date}")
def predictions(date: str):
    pred = _read_pred(date)
    if pred is None:
        raise HTTPException(404, f"无{date}的预测记录")
    detail = _read_detail(date)
    actual_map = {d["code"][-6:]: d for d in detail} if detail else {}
    items = []
    for p in pred["predictions"][:50]:
        code6 = p["code"][-6:]
        a = actual_map.get(code6)
        items.append({
            "code": code6, "name": p["name"],
            "p_up": round(p["p_up"] * 100, 1),
            "p_up5": round(p.get("p_up5", 0) * 100, 1) if p.get("p_up5") is not None else None,
            "p_down5": round(p["p_down5"] * 100, 1),
            "median": round(p["median"], 2),
            "score": round(p["score"], 3),
            "r1": round(p.get("r1", 0), 2),
            "actual": a["actual"] if a else None,
            "hit": a["hit"] if a else None,
        })
    target = next_trading_date(date)
    return {
        "date": date,
        "target_date": target,
        "baseline": pred.get("baseline"),
        "n_samples": pred.get("n_samples"),
        "validated": detail is not None,
        "items": items,
    }


@app.get("/api/detail/{date}")
def detail(date: str):
    d = _read_detail(date)
    if d is None:
        raise HTTPException(404, f"{date}尚未对账")
    return {"date": date, "rows": d}


def _run_pipeline_thread():
    import traceback
    from .pipeline import run_predict
    from .validate import validate_all
    _run_state.update(running=True, log=[], error=None)

    def log(msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        _run_state["log"].append(f"[{ts}] {msg}")

    try:
        log("开始对账旧预测...")
        added = validate_all()
        log(f"对账完成, 新增{len(added)}条记录")
        log("拉取快照+建历史库+打分...")
        result = run_predict()
        if not result["predictions"]:
            raise DataError("无候选股(快照为空或过滤后无满足条件的股票)")
        td = result["trade_date"]
        pred_file = os.path.join(config.PRED_DIR, f"pred_{td}.json")
        if not os.path.exists(pred_file):
            with open(pred_file, "w", encoding="utf-8") as fp:
                json.dump(result, fp, ensure_ascii=False, indent=1)
            log(f"预测已保存: pred_{td}.json (目标日: {next_trading_date(td) or '待定'})")
        else:
            log(f"pred_{td}.json 已存在, 跳过")
        log(f"完成: 数据日期={td}, 历史样本={result['n_samples']}, "
            f"基准上涨率={result['baseline']*100:.1f}%")
        _run_state["last_done"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        _run_state["error"] = f"{type(e).__name__}: {e}"
        log(f"失败: {e}")
        log(traceback.format_exc()[-500:])
    finally:
        _run_state["running"] = False


@app.post("/api/run")
def run_now():
    """手动触发每日流程"""
    if _run_state["running"]:
        return {"ok": False, "msg": "正在运行中"}
    threading.Thread(target=_run_pipeline_thread, daemon=True).start()
    return {"ok": True, "msg": "已启动"}


@app.get("/api/run_status")
def run_status():
    return _run_state


# ---- 静态前端 ----
_dist = os.path.join(config.BASE_DIR, "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = os.path.join(_dist, path)
        if path and os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(_dist, "index.html"))


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
