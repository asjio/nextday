# -*- coding: utf-8 -*-
"""NextDay v2 Web服务: FastAPI单文件内嵌HTML
启动: python -m nextday_v2.web  (或双击 web_v2.bat)
端口: 8767 (v1用8766)
"""
import datetime
import json
import os
import threading
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from . import config
from .backtest import load_result as load_backtest
from .validate import load_history, calibrated_stats

PORT = 8767
app = FastAPI(title="NextDay v2")

_run_state = {"running": False, "log": [], "last_done": None, "error": None}
_bt_state = {"running": False, "log": [], "last_done": None, "error": None}


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


def _live_summary(records):
    """实测统计: 胜率/均涨/累计/最差/信号日/空仓日"""
    open_days = [r for r in records if r.get("gate_open", True) and r.get("n", 0) > 0]
    closed_days = [r for r in records if not r.get("gate_open", True)]
    s = {"hit_rate": None, "avg_actual": None, "cum_actual": None,
         "worst_day": None, "signal_days": len(open_days),
         "closed_days": len(closed_days)}
    if open_days:
        tot_n = sum(r["n"] for r in open_days)
        s["hit_rate"] = round(sum(r["hit_rate"] * r["n"] for r in open_days) / tot_n * 100, 1)
        s["avg_actual"] = round(sum(r["avg_actual"] for r in open_days) / len(open_days), 2)
        cum = 1.0
        for r in sorted(open_days, key=lambda x: x["pred_date"]):
            cum *= 1 + r["avg_actual"] / 100
        s["cum_actual"] = round((cum - 1) * 100, 1)
        s["worst_day"] = round(min(r["avg_actual"] for r in open_days), 2)
    return s


@app.get("/api/overview")
def overview():
    records = load_history()
    stats = calibrated_stats(records)
    summary = _live_summary(records)
    latest_gate = None
    dates = _list_dates()
    if dates:
        latest = _read_pred(dates[0])
        if latest:
            latest_gate = {
                "date": dates[0],
                "gate_open": latest.get("gate_open"),
                "reason": latest.get("gate_closed_reason"),
                "market": latest.get("market"),
                "buy_date": latest.get("buy_date"),
                "sell_date": latest.get("sell_date"),
            }
    bt = load_backtest()
    bt_top20 = None
    if bt and bt.get("topn", {}).get("20"):
        t = bt["topn"]["20"]
        bt_top20 = {"win_rate": t["win_rate"], "avg_ret": t["avg_ret"],
                    "cum_ret": t["cum_ret"], "n_signals": bt["n_signals"],
                    "data_range": bt["data_range"]}
    return {
        "summary": summary,
        "calibrated": stats,
        "latest_gate": latest_gate,
        "bt_top20": bt_top20,
        "recent": sorted(records, key=lambda r: r["pred_date"], reverse=True)[:15],
    }


@app.get("/api/winrate")
def winrate():
    records = [r for r in load_history() if r.get("gate_open", True) and r.get("n", 0) > 0]
    records.sort(key=lambda r: r["pred_date"])
    return {"records": records}


@app.get("/api/predictions/dates")
def pred_dates():
    validated = {r["pred_date"]: True for r in load_history()}
    gates = {}
    for d in _list_dates():
        p = _read_pred(d)
        if p is not None:
            gates[d] = bool(p.get("gate_open"))
    return {"dates": _list_dates(), "validated": validated, "gates": gates}


@app.get("/api/predictions/{date}")
def predictions(date: str):
    pred = _read_pred(date)
    if pred is None:
        raise HTTPException(404, f"无{date}的预测记录")
    detail = _read_detail(date)
    actual_map = {d["code"]: d for d in detail} if detail else {}
    items = []
    for p in pred["predictions"]:
        a = actual_map.get(p["code"])
        items.append({
            "code": p["code"][-6:],
            "name": p["name"],
            "rank": p.get("rank"),
            "momentum20": p.get("momentum20"),
            "r1": p.get("r1"),
            "at_limit_up": p.get("at_limit_up", False),
            "ltsz": p.get("ltsz"),
            "actual": a["actual"] if a else None,
            "hit": a["hit"] if a else None,
        })
    return {
        "date": date,
        "gate_open": pred.get("gate_open"),
        "gate_closed_reason": pred.get("gate_closed_reason"),
        "market": pred.get("market"),
        "buy_date": pred.get("buy_date"),
        "sell_date": pred.get("sell_date"),
        "validated": detail is not None,
        "items": items,
    }


@app.get("/api/backtest")
def backtest_get():
    return {"result": load_backtest(), "state": _bt_state}


def _run_backtest_thread():
    import traceback
    from .backtest import run_backtest
    _bt_state.update(running=True, log=[], error=None)

    def log(msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        _bt_state["log"].append(f"[{ts}] {msg}")

    try:
        log("用本地K线缓存+新浪真实指数回测(walk-forward)...")
        r = run_backtest()
        t20 = r["topn"].get("20", {})
        log(f"完成: {r['data_range'][0]}~{r['data_range'][1]} {r['n_signals']}信号日 "
            f"Top20胜率{t20.get('win_rate', 0)*100:.0f}% 日均{t20.get('avg_ret', 0):+.2f}%")
        _bt_state["last_done"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        _bt_state["error"] = f"{type(e).__name__}: {e}"
        log(f"失败: {e}")
        log(traceback.format_exc()[-300:])
    finally:
        _bt_state["running"] = False


@app.post("/api/backtest/run")
def backtest_run():
    if _bt_state["running"]:
        return {"ok": False, "msg": "回测运行中"}
    threading.Thread(target=_run_backtest_thread, daemon=True).start()
    return {"ok": True, "msg": "已启动"}


def _run_pipeline_thread():
    import traceback
    from .engine import run_predict
    from .validate import validate_all
    _run_state.update(running=True, log=[], error=None)

    def log(msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        _run_state["log"].append(f"[{ts}] {msg}")

    try:
        log("对账旧预测...")
        added = validate_all()
        log(f"对账完成, 新增{len(added)}条")
        log("拉排行+K线+指数, 生成今日信号...")
        result = run_predict()
        td = result["trade_date"]
        pred_file = os.path.join(config.PRED_DIR, f"pred_{td}.json")
        with open(pred_file, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=1)
        if result["gate_open"]:
            log(f"完成: {td} 闸门开, 出信号{len(result['predictions'])}只")
        else:
            log(f"完成: {td} 闸门关闭({result['gate_closed_reason']}), 空仓")
        log("更新回测(缓存数据)...")
        try:
            from .backtest import run_backtest
            run_backtest()
            log("回测更新完成")
        except Exception as e:
            log(f"回测跳过: {e}")
        _run_state["last_done"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        _run_state["error"] = f"{type(e).__name__}: {e}"
        log(f"失败: {e}")
        log(traceback.format_exc()[-400:])
    finally:
        _run_state["running"] = False


@app.post("/api/run")
def run_now():
    if _run_state["running"]:
        return {"ok": False, "msg": "正在运行中"}
    threading.Thread(target=_run_pipeline_thread, daemon=True).start()
    return {"ok": True, "msg": "已启动"}


@app.get("/api/run_status")
def run_status():
    return _run_state


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NextDay v2 动量选股台账</title>
<script src="https://registry.npmmirror.com/echarts/5.5.0/files/dist/echarts.min.js"></script>
<style>
:root {
  --paper: #f7f6f4; --card: #ffffff; --ink: #1f2328; --ink-soft: #57606a;
  --ink-faint: #8b949e; --line: #e6e4e0;
  --rise: #cf3f3f; --rise-soft: #fdf0ef;
  --fall: #2a9d6f; --fall-soft: #ecf7f2;
  --accent: #2f6fed;
}
* { margin:0; padding:0; box-sizing:border-box; }
html, body { background:var(--paper); }
body { font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; color:var(--ink); font-size:14px; }
.font-display { font-family:"Source Han Serif SC","Noto Serif SC","SimSun",serif; }
.font-num { font-family:"Consolas","SF Mono","Menlo",monospace; font-variant-numeric:tabular-nums; }
button, a { cursor:pointer; }
button:disabled { cursor:not-allowed; opacity:.5; }
.wrap { max-width:1150px; margin:0 auto; padding:28px 16px 60px; }
header h1 { font-size:24px; font-weight:600; }
header .sub { color:var(--ink-faint); font-size:12px; margin-top:4px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; }
.banner { display:flex; align-items:center; gap:14px; padding:14px 20px; border-radius:8px; margin:16px 0; font-size:13px; flex-wrap:wrap; }
.banner.open { background:var(--rise-soft); border:1px solid #f3caca; }
.banner.closed { background:var(--fall-soft); border:1px solid #cde9dd; }
.banner .tag { font-weight:700; font-size:15px; }
.banner.open .tag { color:var(--rise); }
.banner.closed .tag { color:var(--fall); }
.banner .meta { color:var(--ink-soft); font-size:12px; }
.stats { display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-bottom:16px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }
.stat .v { font-size:22px; font-weight:600; }
.stat .v.good { color:var(--rise); }
.stat .v.bad { color:var(--fall); }
.stat .k { color:var(--ink-faint); font-size:11px; margin-top:3px; }
.stat .k .tip { border-bottom:1px dashed #c9c6c0; cursor:help; }
section { margin-top:20px; }
.sechead { display:flex; align-items:baseline; justify-content:space-between; margin-bottom:10px; flex-wrap:wrap; gap:8px; }
.sechead h2 { font-size:15px; font-weight:600; }
.sechead .hint { font-size:11px; color:var(--ink-faint); }
.weekbar { display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap; }
.weekbar .nav { padding:5px 14px; font-size:12px; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--ink-soft); }
.weekbar .nav:hover { border-color:var(--ink-faint); }
.weekbar .label { font-size:13px; color:var(--ink-soft); font-weight:500; }
.datebar { display:flex; gap:8px; flex-wrap:wrap; }
.datebtn { padding:6px 14px; font-size:12px; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--ink-soft); transition:all .15s; }
.datebtn:hover { border-color:var(--ink-faint); }
.datebtn.active { background:var(--ink); color:#fff; border-color:var(--ink); }
.datebtn.signal { background:var(--rise-soft); border-color:#f0c3c3; color:var(--rise); font-weight:600; }
.datebtn.signal:hover { border-color:var(--rise); }
.datebtn.signal.active { background:var(--rise); border-color:var(--rise); color:#fff; }
.datebtn.closed { color:var(--ink-faint); background:#f2f1ee; }
.daymeta { font-size:12px; color:var(--ink-soft); margin:12px 0 8px; display:flex; gap:16px; flex-wrap:wrap; align-items:center; }
.daymeta b { color:var(--ink); }
.tag-hit, .tag-miss, .tag-warn, .tag-sig { display:inline-block; font-size:11px; padding:1px 8px; border-radius:3px; }
.tag-hit { color:var(--rise); background:var(--rise-soft); }
.tag-miss { color:var(--fall); background:var(--fall-soft); }
.tag-warn { color:#b07800; background:#fdf6e3; }
.tag-sig { color:#fff; background:var(--rise); }
.tblwrap { overflow-y:auto; max-height:540px; border-radius:8px; }
.tblwrap.short { max-height:340px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
thead th { position:sticky; top:0; background:var(--paper); color:var(--ink-soft); font-weight:500; font-size:12px; text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); white-space:nowrap; z-index:1; }
thead th.tip { cursor:help; border-bottom:1px dashed; }
tbody td { padding:9px 12px; border-bottom:1px solid #f0eee9; white-space:nowrap; }
tbody tr:hover { background:#faf9f7; }
tbody tr.row-fall { background:var(--fall-soft); }
tbody tr.row-fall:hover { background:#e2f2ea; }
.num { text-align:right; }
.up { color:var(--rise); } .down { color:var(--fall); }
.btn { padding:6px 16px; font-size:13px; border-radius:6px; border:1px solid var(--line); background:var(--card); color:var(--ink); }
.btn:hover { background:#faf9f7; }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
.btn.primary:hover { opacity:.9; }
.runlog { font-family:Consolas,monospace; font-size:12px; color:var(--ink-soft); white-space:pre-wrap; margin-top:10px; max-height:140px; overflow-y:auto; display:none; }
#chart { width:100%; height:300px; }
.empty { color:var(--ink-faint); padding:30px 0; text-align:center; font-size:13px; }
.bthead { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
.bthead h2 { font-size:15px; font-weight:600; }
.bthead .meta { font-size:11px; color:var(--ink-faint); }
.btgrid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.btgrid .lbl { font-size:12px; color:var(--ink-soft); font-weight:600; margin-bottom:6px; }
footer { text-align:center; color:var(--ink-faint); font-size:11px; padding:28px 0 4px; }
@media (max-width:900px) { .stats { grid-template-columns:repeat(3,1fr); } .btgrid { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 class="font-display">NextDay v2 动量选股台账</h1>
    <p class="sub">动量20日选股 · 复合情绪闸门(指数MA10 + 市场宽度55% + 涨停家数>8) · 买入日临近收盘买入 / 卖出日收盘卖出 · 逐日实测对账</p>
  </header>

  <div id="gate"></div>
  <div class="stats" id="stats"></div>

  <section class="card" style="padding:16px 18px;">
    <div class="sechead">
      <h2>胜率曲线 (闸门开启日逐日对账)</h2>
      <span class="hint">x轴=信号日 · 卖出日收盘后自动对账</span>
    </div>
    <div id="chart"></div>
    <div id="chartempty" class="empty" style="display:none;">暂无对账数据</div>
  </section>

  <section class="card" style="padding:16px 18px;">
    <div class="bthead">
      <h2>策略回测 <span class="hint" style="font-weight:400">真实上证指数口径 · walk-forward · 闸门与实盘完全一致</span></h2>
      <div style="display:flex; align-items:center; gap:10px;">
        <span class="meta" id="btmeta"></span>
        <button class="btn" id="btbtn" onclick="runBacktest()">执行回测</button>
      </div>
    </div>
    <div id="btlog" class="runlog"></div>
    <div id="btbody">
      <div class="btgrid">
        <div>
          <div class="lbl">TopN 买入档位对比 <span class="hint">(等权持有1天, 信号日次日持有)</span></div>
          <div class="tblwrap short card"><table>
            <thead><tr>
              <th class="tip" title="按20日动量排序取前N只, 等权买入">买法</th>
              <th class="num tip" title="收益>0的信号日占比">胜率</th>
              <th class="num">日均</th><th class="num">累计</th>
              <th class="num tip" title="历史信号日中最差的一天">最差日</th>
              <th class="num">亏损日</th>
            </tr></thead>
            <tbody id="bttbody"></tbody>
          </table></div>
        </div>
        <div>
          <div class="lbl">信号日逐日收益 <span class="hint">(红=赚 绿=亏)</span></div>
          <div class="tblwrap short card"><table>
            <thead><tr><th>信号日</th><th class="num">涨停家数</th><th class="num">宽度</th><th class="num">Top5</th><th class="num">Top10</th><th class="num">Top20</th></tr></thead>
            <tbody id="btdays"></tbody>
          </table></div>
        </div>
      </div>
    </div>
    <div id="btempty" class="empty" style="display:none;">暂无回测结果, 点击右上角"执行回测"(或等每日流程自动运行)</div>
  </section>

  <section>
    <div class="sechead">
      <h2>预测台账</h2>
      <button class="btn primary" id="runbtn" onclick="runNow()">立即执行每日流程</button>
    </div>
    <div id="runlog" class="runlog"></div>

    <div class="weekbar">
      <button class="nav" id="prevweek" onclick="shiftWeek(1)">上一周</button>
      <span class="label" id="weeklabel"></span>
      <button class="nav" id="nextweek" onclick="shiftWeek(-1)">下一周</button>
    </div>
    <div class="datebar" id="datebar"></div>
    <p class="hint" style="margin:6px 0 0; font-size:11px; color:var(--ink-faint);">红底=闸门开启可买入的信号日, 灰底=闸门关闭空仓日</p>

    <div class="daymeta" id="daymeta"></div>
    <div class="card tblwrap">
      <table>
        <thead><tr>
          <th>序</th><th>代码</th><th>名称</th>
          <th class="tip" title="过去20个交易日累计涨幅, 按此排序选股">20日动量</th>
          <th class="tip" title="信号日当天实际涨跌幅">信号日涨幅</th>
          <th class="tip" title="流通市值(亿元)">市值(亿)</th>
          <th class="tip num" title="卖出日收盘的实际收益(对账后显示)">实际收益</th>
          <th class="tip" title="对账结果: 实际收益>0为命中">对账</th>
        </tr></thead>
        <tbody id="sigbody"></tbody>
      </table>
    </div>
    <p class="hint" style="margin-top:8px; font-size:11px; color:var(--ink-faint);">
      信号日涨幅标注[已涨停]: 次日无法买入或追高风险大, 仅作提示。跌的行以浅绿底标出(与v1一致)。
    </p>
  </section>

  <section class="card" style="padding:16px 18px;">
    <div class="sechead"><h2>对账历史</h2><span class="hint">闸门关闭日 = 空仓避险, 不参与</span></div>
    <div class="tblwrap"><table>
      <thead><tr>
        <th>信号日</th><th>卖出日</th><th>状态</th>
        <th class="num tip" title="组合中实际收益>0的股票数/总数">命中数</th>
        <th class="num tip" title="命中数/总数, 组合层面胜率">命中率</th>
        <th class="num tip" title="组合等权平均单日收益">均收益</th>
      </tr></thead>
      <tbody id="histbody"></tbody>
    </table></div>
  </section>

  <footer>防守型策略: 市场情绪不足时空仓不参与, 牺牲信号频率换胜率(回测信号约每月1次) · 概率预测非投资建议 · 数据源: 腾讯/新浪财经</footer>
</div>

<script>
const $ = s => document.querySelector(s);
const fmtPct = (v, signed=false) => {
  if (v === null || v === undefined) return "--";
  const s = signed && v > 0 ? "+" : "";
  return s + Number(v).toFixed(2) + "%";
};
let ALL_DATES = [], VALIDATED = {}, GATES = {}, curDate = null, curWeek = 0;

function toISO(d) {
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}
function weekKey(dstr) {
  const p = dstr.split('-').map(Number);
  const d = new Date(p[0], p[1]-1, p[2]);
  const dow = (d.getDay() + 6) % 7; // 周一=0
  d.setDate(d.getDate() - dow);
  return toISO(d);
}
function groupByWeek(dates) {
  const m = {};
  dates.forEach(d => { (m[weekKey(d)] = m[weekKey(d)] || []).push(d); });
  return Object.keys(m).sort().reverse().map(wk => ({ wk, dates: m[wk].slice().sort().reverse() }));
}

async function load() {
  const ov = await (await fetch('/api/overview')).json();
  const g = ov.latest_gate;
  if (g) {
    const mk = g.market || {};
    const meta = `指数 ${mk.index_close ? mk.index_close.toFixed(0) : '-'} / MA10 ${mk.ma_gate ? mk.ma_gate.toFixed(0) : '-'} / 上涨占比 ${mk.breadth != null ? (mk.breadth*100).toFixed(0)+'%' : '-'} / 涨停 ${mk.zt_count != null ? mk.zt_count : '-'}家`;
    if (g.gate_open) {
      $('#gate').innerHTML = `<div class="banner open"><span class="tag">闸门: 开</span>
        <span>${g.date} 出信号 · 买入 <b>${g.buy_date}</b> 临近收盘 · 卖出 <b>${g.sell_date}</b> 收盘</span>
        <span class="meta">${meta}</span></div>`;
    } else {
      $('#gate').innerHTML = `<div class="banner closed"><span class="tag">闸门: 关</span>
        <span>${g.date} 空仓 · ${g.reason || ''}</span><span class="meta">${meta}</span></div>`;
    }
  }
  const s = ov.summary || {}, c = ov.calibrated || {}, bt20 = ov.bt_top20;
  const cells = [
    { k: "实测胜率", tip: `实盘对账${c.n_days||0}天的组合胜率(个股收益>0占比加权)`,
      v: c.n_days ? (c.winrate*100).toFixed(1)+"%" : "--", good: true },
    { k: "回测胜率", tip: bt20 ? `回测区间${bt20.data_range[0]}~${bt20.data_range[1]}, Top20档${bt20.n_signals}个信号日` : "暂无回测",
      v: bt20 ? (bt20.win_rate*100).toFixed(0)+"%" : "--", good: true },
    { k: "实测日均", tip: "实盘信号日组合平均单日收益",
      v: s.avg_actual != null ? fmtPct(s.avg_actual, true) : "--", good: (s.avg_actual||0) >= 0 },
    { k: "实测累计", tip: "实盘信号日复利累计收益(只在信号日持仓)",
      v: s.cum_actual != null ? fmtPct(s.cum_actual, true) : "--", good: (s.cum_actual||0) >= 0 },
    { k: "最差单日", tip: "实盘信号日中最差的一天, 防守目标是压低它",
      v: s.worst_day != null ? fmtPct(s.worst_day, true) : "--", good: false },
    { k: "信号/空仓", tip: "闸门开启出信号天数 / 闸门关闭空仓天数, 不参与就不亏",
      v: `${s.signal_days ?? 0} / ${s.closed_days ?? 0}`, good: false },
  ];
  $('#stats').innerHTML = cells.map(c2 => `<div class="stat">
    <div class="v ${c2.good ? 'good' : ''}">${c2.v}</div>
    <div class="k"><span class="tip" title="${c2.tip}">${c2.k}</span></div></div>`).join('');

  const dd = await (await fetch('/api/predictions/dates')).json();
  ALL_DATES = dd.dates; VALIDATED = dd.validated; GATES = dd.gates || {};
  renderWeek();
  if (!curDate && ALL_DATES.length) setDate(ALL_DATES[0]);

  $('#histbody').innerHTML = ov.recent.map(r => r.gate_open === false
    ? `<tr><td>${r.pred_date}</td><td>-</td><td><span class="tag-miss">空仓</span></td><td class="num">-</td><td class="num">-</td><td class="num">-</td></tr>`
    : `<tr><td>${r.pred_date}</td><td>${r.target_date}</td><td><span class="tag-hit">开仓</span></td>
       <td class="num">${Math.round(r.hit_rate*r.n)}/${r.n}</td>
       <td class="num">${(r.hit_rate*100).toFixed(0)}%</td>
       <td class="num ${r.avg_actual>=0?'up':'down'}">${fmtPct(r.avg_actual,true)}</td></tr>`).join('')
    || '<tr><td colspan="6" class="empty">暂无记录</td></tr>';

  const wr = await (await fetch('/api/winrate')).json();
  if (wr.records.length >= 2) {
    $('#chartempty').style.display = 'none';
    const rs = wr.records;
    let cum = 1;
    const cums = rs.map(r => { cum *= 1 + r.avg_actual/100; return +((cum-1)*100).toFixed(1); });
    const chart = echarts.init($('#chart'));
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['命中率','均收益%','累计收益%'], textStyle: { fontSize: 12 } },
      grid: { left: 48, right: 48, top: 38, bottom: 30 },
      xAxis: { type: 'category', data: rs.map(r => r.pred_date.slice(5)), name: '信号日', nameTextStyle: { fontSize: 11 } },
      yAxis: [ { type: 'value', name: '%', min: 0, max: 100 },
               { type: 'value', name: '收益%', splitLine: { show: false } } ],
      series: [
        { name: '命中率', type: 'line', data: rs.map(r => +(r.hit_rate*100).toFixed(1)), itemStyle: { color: '#cf3f3f' } },
        { name: '均收益%', type: 'bar', yAxisIndex: 1, data: rs.map(r => r.avg_actual),
          itemStyle: { color: p => p.value >= 0 ? '#cf3f3f' : '#2a9d6f' } },
        { name: '累计收益%', type: 'line', yAxisIndex: 1, smooth: true, data: cums, itemStyle: { color: '#2f6fed' } },
      ]
    });
    window.addEventListener('resize', () => chart.resize());
  } else { $('#chart').style.display = 'none'; $('#chartempty').style.display = 'block'; }

  loadBacktest();
}

async function loadBacktest() {
  const b = await (await fetch('/api/backtest')).json();
  const r = b.result;
  if (!r || !r.topn) { $('#btbody').style.display = 'none'; $('#btempty').style.display = 'block'; return; }
  $('#btbody').style.display = '';
  $('#btempty').style.display = 'none';
  $('#btmeta').textContent = `${r.data_range[0]} ~ ${r.data_range[1]} · ${r.n_signals}个信号日 · 更新于 ${r.run_at}`;
  $('#bttbody').innerHTML = Object.keys(r.topn).sort((a,b)=>a-b).map(k => {
    const t = r.topn[k];
    const hl = k === '20' ? ' style="font-weight:600"' : '';
    return `<tr${hl}><td>Top${k}${k==='20'?' (现行)':''}</td>
      <td class="num font-num">${(t.win_rate*100).toFixed(0)}%</td>
      <td class="num font-num ${t.avg_ret>=0?'up':'down'}">${fmtPct(t.avg_ret,true)}</td>
      <td class="num font-num ${t.cum_ret>=0?'up':'down'}">${fmtPct(t.cum_ret,true)}</td>
      <td class="num font-num down">${fmtPct(t.worst,true)}</td>
      <td class="num font-num">${t.loss_days}天</td></tr>`;
  }).join('');
  $('#btdays').innerHTML = r.days.slice().reverse().map(d => {
    const cell = v => `<td class="num font-num ${v>=0?'up':'down'}">${fmtPct(v,true)}</td>`;
    return `<tr><td>${d.date}</td><td class="num font-num">${d.zt_count}</td>
      <td class="num font-num">${(d.breadth*100).toFixed(0)}%</td>${cell(d.top5)}${cell(d.top10)}${cell(d.top20)}</tr>`;
  }).join('');
}

async function runBacktest() {
  const btn = $('#btbtn'); btn.disabled = true;
  $('#btlog').style.display = 'block';
  await fetch('/api/backtest/run', { method: 'POST' });
  const poll = setInterval(async () => {
    const b = await (await fetch('/api/backtest')).json();
    const st = b.state;
    $('#btlog').textContent = st.log.join('\n');
    $('#btlog').scrollTop = 1e9;
    if (!st.running) { clearInterval(poll); btn.disabled = false; loadBacktest(); }
  }, 1000);
}

function renderWeek() {
  const weeks = groupByWeek(ALL_DATES);
  if (!weeks.length) return;
  curWeek = Math.max(0, Math.min(curWeek, weeks.length - 1));
  const w = weeks[curWeek];
  const ds = w.dates.slice().sort();
  $('#weeklabel').textContent = `${ds[ds.length-1]} ~ ${ds[0]} (本周${w.dates.length}天记录)`;
  $('#prevweek').disabled = curWeek >= weeks.length - 1;
  $('#nextweek').disabled = curWeek <= 0;
  $('#datebar').innerHTML = w.dates.map(d => {
    const gopen = GATES[d];
    const cls = gopen === true ? 'datebtn signal' : 'datebtn closed';
    const mark = gopen === true ? ' <span class="tag-sig">信号</span>' : '';
    return `<button class="${cls} ${d===curDate?'active':''}" onclick="setDate('${d}')">${d}${mark}</button>`;
  }).join('');
}
// 上一周=往过去翻(索引+1), 下一周=往新翻(索引-1); 切换周后自动选中该周最新一天
function shiftWeek(d) {
  const weeks = groupByWeek(ALL_DATES);
  const nw = Math.max(0, Math.min(curWeek + d, weeks.length - 1));
  if (nw === curWeek) return;
  curWeek = nw;
  const latest = weeks[curWeek].dates.slice().sort().reverse()[0];
  setDate(latest);
}

async function setDate(d) {
  curDate = d;
  renderWeek();
  const p = await (await fetch('/api/predictions/' + d)).json();
  const mk = p.market || {};
  const meta = [];
  meta.push(`买入 <b>${p.buy_date || '-'}</b> 临近收盘 / 卖出 <b>${p.sell_date || '-'}</b> 收盘`);
  if (mk.breadth != null) meta.push(`当日上涨占比 ${(mk.breadth*100).toFixed(0)}%`);
  if (mk.zt_count != null) meta.push(`当日涨停 ${mk.zt_count}家`);
  meta.push(p.validated ? '<span class="tag-hit">已对账</span>' : '<span style="color:var(--ink-faint)">待卖出日收盘后对账</span>');
  if (p.gate_open === false) {
    $('#daymeta').innerHTML = `<span class="tag-miss">空仓</span> ${p.gate_closed_reason || ''}`;
    $('#sigbody').innerHTML = '<tr><td colspan="8" class="empty">闸门关闭, 当日空仓不出信号</td></tr>';
    return;
  }
  $('#daymeta').innerHTML = `<span class="tag-sig">可买入信号日</span> ` + meta.join('<span style="color:var(--line)">|</span>');
  if (!p.items || !p.items.length) {
    $('#sigbody').innerHTML = '<tr><td colspan="8" class="empty">当日无信号</td></tr>';
    return;
  }
  $('#sigbody').innerHTML = p.items.map(it => {
    const fell = it.hit === false;
    const lim = it.at_limit_up ? ' <span class="tag-warn">已涨停</span>' : '';
    let act = '<span style="color:var(--ink-faint)">--</span>', rec = '<span style="color:var(--ink-faint);font-size:12px">未对账</span>';
    if (it.actual != null) {
      act = `<span class="${it.actual>=0?'up':'down'}">${fmtPct(it.actual,true)}</span>`;
      rec = it.hit ? '<span class="tag-hit">命中</span>' : '<span class="tag-miss">失误</span>';
    }
    return `<tr class="${fell ? 'row-fall' : ''}">
      <td class="font-num" style="color:var(--ink-faint)">${String(it.rank).padStart(2,'0')}</td>
      <td class="font-num">${it.code}</td><td>${it.name}${lim}</td>
      <td class="num font-num up">+${it.momentum20.toFixed(1)}%</td>
      <td class="num font-num ${it.r1>=0?'up':'down'}">${fmtPct(it.r1,true)}</td>
      <td class="num font-num">${it.ltsz != null ? it.ltsz.toFixed(0) : '-'}</td>
      <td class="num font-num">${act}</td><td>${rec}</td></tr>`;
  }).join('');
}

async function runNow() {
  const btn = $('#runbtn'); btn.disabled = true;
  $('#runlog').style.display = 'block';
  await fetch('/api/run', { method: 'POST' });
  const poll = setInterval(async () => {
    const st = await (await fetch('/api/run_status')).json();
    $('#runlog').textContent = st.log.join('\n');
    $('#runlog').scrollTop = 1e9;
    if (!st.running) { clearInterval(poll); btn.disabled = false; curDate = null; curWeek = 0; load(); }
  }, 2000);
}
load();
</script>
</body>
</html>
"""


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
