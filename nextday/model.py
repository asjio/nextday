# -*- coding: utf-8 -*-
"""KNN相似日模型: 建历史库 + 预测次日涨跌概率"""
import numpy as np
from . import config
from .features import build_features


class NextDayModel:
    def __init__(self):
        self.X = None        # 历史特征矩阵
        self.Y = None        # 历史次日收益%
        self.mu = None
        self.sd = None
        self.n_samples = 0

    def build(self, kline_dict):
        """kline_dict: {code: {'name':, 'rows': [[date,o,c,h,l,v],...]}}
        构建历史样本库: 每个交易日特征 + 次日真实收益"""
        lib_x, lib_y = [], []
        self.today_feats = {}   # code -> (name, date, 特征向量)
        for code, rec in kline_dict.items():
            feats = build_features(rec["rows"])
            if feats is None:
                continue
            feat_cols = feats[config.FEATURE_NAMES]
            close = feats["close"]
            nxt = close.shift(-1) / close * 100 - 100
            idx = feat_cols.dropna().index
            idx = idx[(idx >= config.WARMUP) & (idx <= len(feats) - 2)]
            for i in idx:
                lib_x.append(feat_cols.loc[i].values)
                lib_y.append(nxt.loc[i])
            last_i = len(feats) - 1
            if last_i >= config.WARMUP and feat_cols.iloc[-1].notna().all():
                self.today_feats[code] = (rec["name"], feats.iloc[-1]["date"],
                                          feat_cols.iloc[-1].values)
        self.X = np.array(lib_x)
        self.Y = np.array(lib_y)
        self.mu = self.X.mean(0)
        self.sd = self.X.std(0) + 1e-9
        self.n_samples = len(self.X)
        return self

    def _predict_k(self, v, k):
        vs = (v - self.mu) / self.sd
        Xs = (self.X - self.mu) / self.sd
        d = ((Xs - vs) ** 2).sum(1)
        y = self.Y[np.argsort(d)[:k]]
        return {
            "p_up": float((y > 0).mean()),
            "p_up2": float((y > 2).mean()),
            "p_up5": float((y > 5).mean()),
            "p_down5": float((y < -5).mean()),
            "median": float(np.median(y)),
            "mean": float(y.mean()),
        }

    def predict_all(self):
        """对today_feats全部打分, 返回按风险调整分排序的list"""
        k_main = config.K_NEIGHBORS
        results = []
        for code, (name, date, v) in self.today_feats.items():
            ps = {k: self._predict_k(v, k) for k in config.K_STABILITY}
            main = ps[k_main]
            ups = [ps[k]["p_up"] for k in config.K_STABILITY]
            stability = 1 - np.std(ups) / max(main["p_up"], 1e-9)
            score = (main["p_up"] - main["p_down5"] * 1.5) * stability
            results.append({
                "code": code, "name": name, "date": date,
                "p_up": main["p_up"], "p_up2": main["p_up2"],
                "p_up5": main["p_up5"], "p_down5": main["p_down5"],
                "median": main["median"], "score": float(score),
                "stability": float(stability),
                "r1": float(v[0]),
                "ps": {str(k): ps[k]["p_up"] for k in config.K_STABILITY},
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    @property
    def baseline(self):
        return float((self.Y > 0).mean())
