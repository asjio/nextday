# -*- coding: utf-8 -*-
"""nextday_v2 每日入口: 对账旧预测 -> 生成新预测
用法: python -m nextday_v2.main
"""
import datetime
import json
import os
import sys

from . import config
from .engine import run_predict
from .validate import validate_all, load_history, calibrated_stats


def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    print(f"===== NextDay v2 每日流程 {today} =====", flush=True)

    # 1. 对账旧预测
    added = validate_all()
    if added:
        print(f"[对账] 新增{len(added)}条记录:", flush=True)
        for r in added:
            if not r.get("gate_open", True):
                print(f"  {r['pred_date']}: 闸门关闭, 空仓", flush=True)
            else:
                print(f"  {r['pred_date']} -> 卖出日{r['target_date']}: "
                      f"命中{r['hit_rate']*100:.1f}% Top12命中{r['top12_hit_rate']*100:.1f}% "
                      f"均涨{r['avg_actual']:+.2f}%", flush=True)
    else:
        print("[对账] 无新可对账记录", flush=True)

    history = load_history()
    stats = calibrated_stats(history)
    src = "实测校准" if stats["calibrated"] else "回测基准"
    print(f"[胜率基准] {src}: 胜率{stats['winrate']*100:.1f}% "
          f"均涨{stats['avg_ret']:+.2f}% (样本{stats['n_days']}天)", flush=True)

    # 2. 生成今日新预测
    print("[预测] 拉排行+K线+指数, 算动量+闸门...", flush=True)
    try:
        result = run_predict()
    except Exception as e:
        print(f"[预测] 失败: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)

    td = result["trade_date"]
    pred_file = os.path.join(config.PRED_DIR, f"pred_{td}.json")
    with open(pred_file, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=1)
    print(f"[预测] 已存 {pred_file}", flush=True)
    print(f"[预测] 数据日期={td} 股票池={result['n_pool']} 有效K线={result['n_kline_ok']}", flush=True)

    m = result["market"]
    print(f"[大盘] 指数{m['index_close']:.0f} MA{config.GATE_MA}={m['ma_gate']:.0f} "
          f"上涨占比={m['breadth']*100:.0f}%(阈值{m['breadth_th']*100:.0f}%) "
          f"状态={m['market_state']} 闸门={'开' if m['gate_open'] else '关'}", flush=True)

    if not result["gate_open"]:
        print(f"\n[空仓] {result['gate_closed_reason']}, 今日不出信号", flush=True)
    else:
        print(f"\n--- 今日TOP{len(result['predictions'])} "
              f"(买入{result['buy_date']}临近收盘, 卖出{result['sell_date']}收盘) ---", flush=True)
        print(f"{'排名':<4}{'代码':<8}{'名称':<10}{'20日动量':>9}{'今日涨幅':>9}{'市值亿':>8}", flush=True)
        for p in result["predictions"]:
            mark = " [已涨停]" if p["at_limit_up"] else ""
            print(f"{p['rank']:<4}{p['code'][-6:]:<8}{p['name']:<10}"
                  f"{p['momentum20']:>+8.1f}%{p['r1']:>+8.1f}%{p['ltsz']:>8.0f}{mark}", flush=True)

    # 3. 回测(用每日更新的K线缓存, 随数据自动延伸), 失败不影响主流程
    try:
        from .backtest import run_backtest
        bt = run_backtest()
        t20 = bt["topn"].get("20", {})
        print(f"[回测] {bt['data_range'][0]}~{bt['data_range'][1]} "
              f"{bt['n_signals']}信号日 Top20胜率{t20.get('win_rate', 0)*100:.0f}% "
              f"日均{t20.get('avg_ret', 0):+.2f}% 累计{t20.get('cum_ret', 0):+.1f}%", flush=True)
    except Exception as e:
        print(f"[回测] 跳过: {type(e).__name__}: {e}", flush=True)

    print("===== 完成 =====", flush=True)


if __name__ == "__main__":
    main()
