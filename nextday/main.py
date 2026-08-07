# -*- coding: utf-8 -*-
"""每日入口: 对账旧预测 -> 生成新预测 -> 更新胜率曲线
用法: python -m nextday.main
"""
import json
import os
import sys
import datetime

from . import config
from .pipeline import run_predict
from .validate import validate_all, load_history
from .report import plot_winrate, text_summary


def today_str():
    return datetime.date.today().strftime("%Y-%m-%d")


def main():
    print(f"===== NextDay 每日流程 {today_str()} =====", flush=True)

    # 1. 对账旧预测
    added = validate_all()
    if added:
        print(f"[对账] 新增{len(added)}条验证记录:", flush=True)
        for r in added:
            print(f"  预测日{r['pred_date']} -> 目标日{r['target_date']}: "
                  f"全体命中{r['hit_rate']*100:.1f}% Top12命中{r['top12_hit_rate']*100:.1f}%",
                  flush=True)
    else:
        print("[对账] 无新可对账记录", flush=True)

    # 2. 生成今日新预测
    print("[预测] 拉快照+建历史库+打分...", flush=True)
    try:
        result = run_predict()
    except Exception as e:
        print(f"[预测] 失败: {type(e).__name__}: {e}", flush=True)
        sys.exit(1)
    if not result["predictions"]:
        print("[预测] 失败: 快照正常但无候选股(可能全部不满足收涨+主力净流入条件)", flush=True)
        sys.exit(1)
    td = result["trade_date"]
    pred_file = os.path.join(config.PRED_DIR, f"pred_{td}.json")
    if not os.path.exists(pred_file):
        with open(pred_file, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=1)
        print(f"[预测] 已存 {pred_file}", flush=True)
    else:
        print(f"[预测] {pred_file} 已存在, 跳过", flush=True)

    print(f"[预测] 数据日期={td} 历史样本={result['n_samples']} "
          f"基准上涨率={result['baseline']*100:.1f}%", flush=True)
    print("\n--- 今日TOP10 (明日上涨概率) ---", flush=True)
    print(f"{'代码':<8}{'名称':<10}{'P涨':>7}{'P>5%':>7}{'P大跌':>7}{'次日中位':>9}", flush=True)
    for p in result["predictions"][:10]:
        print(f"{p['code'][-6:]:<8}{p['name']:<10}{p['p_up']*100:>6.1f}%"
              f"{p['p_up5']*100:>6.1f}%{p['p_down5']*100:>6.1f}%{p['median']:>8.2f}%",
              flush=True)

    # 3. 胜率曲线
    records = load_history()
    if records:
        img = plot_winrate(records)
        print(f"\n[报告] 胜率曲线: {img}", flush=True)
        print("[累计统计]", flush=True)
        print(text_summary(records), flush=True)
    else:
        print("\n[报告] 胜率记录为空(首次运行, 明天起有对账数据)", flush=True)
    print("===== 完成 =====", flush=True)


if __name__ == "__main__":
    main()
