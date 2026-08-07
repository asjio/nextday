# -*- coding: utf-8 -*-
"""回填: 8/5旧预测 -> nextday格式"""
import json, os
from nextday import config
from nextday.datasource import full_code

OLD = r"C:\Users\e-Zilong.Shang\quant_final.json"
preds = json.load(open(OLD, encoding="utf-8"))
out = []
for p in preds:
    out.append({
        "code": full_code(p["code"]),
        "name": p["name"],
        "date": "2026-08-05",
        "p_up": p["p60"],
        "p_up5": None,
        "p_down5": p["down5"],
        "median": p["med"],
        "score": p["score"] / 100,
        "r1": p["r1"],
    })
result = {
    "trade_date": "2026-08-05",
    "baseline": 0.492,
    "n_samples": 113541,
    "n_universe": 203,
    "n_kline_ok": 201,
    "predictions": out,
}
path = os.path.join(config.PRED_DIR, "pred_2026-08-05.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print("回填完成:", path, len(out), "条")
