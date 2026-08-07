# -*- coding: utf-8 -*-
"""特征提取: 日线 -> 7维形态向量"""
import numpy as np
import pandas as pd


def build_features(rows):
    """rows: [[date,open,close,high,low,volume],...] -> DataFrame(7特征, 按日)"""
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    for c in ["open", "close", "high", "low", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    if len(df) < 70:
        return None
    c = df["close"]
    feats = pd.DataFrame({
        "r1": c.pct_change() * 100,
        "m5": c.pct_change(5) * 100,
        "m20": c.pct_change(20) * 100,
        "m60": c.pct_change(60) * 100,
        "pos60": (c - c.rolling(60).min()) / (c.rolling(60).max() - c.rolling(60).min() + 1e-9),
        "vr": df["volume"] / (df["volume"].rolling(20).mean() + 1e-9),
        "big_up": (c.pct_change() * 100 >= 9.5).astype(float),
    })
    feats["date"] = df["date"].values
    feats["close"] = c.values
    return feats
