# -*- coding: utf-8 -*-
"""报告模块: 胜率曲线 + 文本摘要"""
import os
from . import config
from .validate import load_history

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 中文字体
for _f in ["Microsoft YaHei", "SimHei", "DengXian"]:
    if any(_f.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [_f]
        break
plt.rcParams["axes.unicode_minus"] = False


def divergence_section(records=None):
    """Top12 vs 全体背离监控: Top12是专门挑的, 跑输全体说明选股逻辑与市场风格冲突"""
    records = records or load_history()
    if not records:
        return ""
    lines = []
    recent = records[-5:]
    for r in recent:
        d_hit = (r["top12_hit_rate"] - r["hit_rate"]) * 100
        d_ret = r["top12_avg"] - r["avg_actual"]
        flag = "正常" if d_ret >= 0 else "背离"
        lines.append(f"  {r['target_date']}: 命中率差{d_hit:+.1f}pct 收益差{d_ret:+.2f}pct [{flag}]")
    streak = 0
    for r in reversed(records):
        if r["top12_avg"] - r["avg_actual"] < 0:
            streak += 1
        else:
            break
    if streak >= 3:
        lines.append(f"  [警告] Top12已连续{streak}天跑输全体, 选股逻辑可能与当前市场风格冲突")
    return "\n".join(lines)


def plot_winrate(records=None, out_path=None):
    """胜率曲线: 全体/Top12/高置信组 三条命中率 + 基准线"""
    records = records or load_history()
    if len(records) < 1:
        return None
    out_path = out_path or os.path.join(config.REPORT_DIR, "winrate_curve.png")

    dates = [r["target_date"][5:] for r in records]
    all_hr = [r["hit_rate"] * 100 for r in records]
    t12_hr = [r["top12_hit_rate"] * 100 for r in records]
    hc_hr = [r["high_conf_hit_rate"] * 100 if r["high_conf_hit_rate"] is not None else None
             for r in records]
    avg_act = [r["avg_actual"] for r in records]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    x = range(len(dates))
    ax1.plot(x, all_hr, "o-", label="全体命中率", color="#4a90d9", linewidth=2)
    ax1.plot(x, t12_hr, "s-", label="Top12命中率", color="#e8a33d", linewidth=2)
    ax1.plot(x, hc_hr, "^-", label="高置信(P>=70%)命中率", color="#d9534f", linewidth=2)
    ax1.axhline(49.2, color="gray", linestyle="--", linewidth=1, label="随机基准 49.2%")
    ax1.set_ylabel("次日上涨命中率 (%)")
    ax1.set_ylim(0, 105)
    ax1.set_title("NextDay 模型胜率曲线 (逐日真实验证)", fontsize=13)
    ax1.legend(loc="lower right", fontsize=9)
    ax1.grid(alpha=0.3)
    for i, v in enumerate(all_hr):
        ax1.annotate(f"{v:.0f}", (i, v), textcoords="offset points", xytext=(0, 6),
                     fontsize=8, ha="center", color="#4a90d9")

    ax2.bar(x, avg_act, color=["#5cb85c" if v >= 0 else "#d9534f" for v in avg_act])
    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.set_ylabel("全体平均收益 (%)")
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(dates, rotation=30, fontsize=9)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=110)
    plt.close()
    return out_path


def text_summary(records=None):
    """文本摘要: 累计胜率统计"""
    records = records or load_history()
    if not records:
        return "暂无验证记录"
    n_days = len(records)
    tot_n = sum(r["n"] for r in records)
    w_all = sum(r["hit_rate"] * r["n"] for r in records) / tot_n * 100
    tot_t12 = sum(r["top12_hit_rate"] for r in records) / n_days * 100
    hc = [r for r in records if r["high_conf_hit_rate"] is not None]
    w_hc = sum(r["high_conf_hit_rate"] for r in hc) / len(hc) * 100 if hc else None
    avg_all = sum(r["avg_actual"] for r in records) / n_days
    lines = [
        f"累计验证: {n_days}个交易日, {tot_n}个样本",
        f"全体命中率: {w_all:.1f}% (随机基准49.2%)",
        f"Top12命中率: {tot_t12:.1f}%",
    ]
    if w_hc is not None:
        lines.append(f"高置信(P>=70%)命中率: {w_hc:.1f}%")
    lines.append(f"全体平均次日收益: {avg_all:+.2f}%")
    return "\n".join(lines)
