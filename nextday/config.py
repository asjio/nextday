# -*- coding: utf-8 -*-
"""项目配置"""
import os

# 目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PRED_DIR = os.path.join(DATA_DIR, "predictions")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
for _d in (DATA_DIR, PRED_DIR, REPORT_DIR):
    os.makedirs(_d, exist_ok=True)

# 候选池
TOP_N_BY_STRENGTH = 100    # 按资金强度(主力净流入/流通市值)取前N
RANDOM_N = 100             # 随机对照样本数(历史库需要下跌样本)
MIN_PRICE = 3.0            # 剔除低价股
MIN_LTSZ = 25.0            # 剔除流通市值<25亿
EXCLUDE_PREFIX = ("8", "4", "9")   # 剔除北交所/B股

# 显式跟踪代码(带前缀)
TRACK_CODES = ["sz300248", "sz300986", "sz000981", "sz000712", "sz001337",
               "sz300615", "sz300209", "sz003032", "sz300552", "sz301026"]

# 模型
KLINE_LEN = 640            # 历史K线长度(交易日)
WARMUP = 65                # 特征预热期, 前N天不做样本
K_NEIGHBORS = 60           # 相似日数量
K_STABILITY = (30, 60, 100)  # 稳健性检验的K档位

# 特征列名(顺序固定, 勿改)
FEATURE_NAMES = ["r1", "m5", "m20", "m60", "pos60", "vr", "big_up"]
