# -*- coding: utf-8 -*-
"""nextday_v2 配置
策略: 动量20日选股 + 复合情绪闸门(指数MA10 + 市场宽度55% + 池内涨停家数>8)
回测依据(2025.4~2026.8, 全A流通市值前300, walk-forward, 次日持有Top20, 真实上证指数口径):
  闸门=指数>MA10 且 宽度>55% 且 涨停家数>8:
  14信号日胜率93%, 日均涨+2.14%, 累计+31.7%, 最差单日-1.93%, 亏损日仅1天
  分年度: 2025年7天100%, 2026年7天86%
设计目标: 不亏优先。代价是信号稀缺(约每月1次), 大部分时间空仓。
情绪分量含义: 宽度=市场情绪广度; 涨停家数=活跃资金进攻强度
交易语义: t日收盘出信号 -> t+1日临近收盘买入 -> t+2日收盘卖出
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "v2")
PRED_DIR = os.path.join(DATA_DIR, "predictions")
os.makedirs(PRED_DIR, exist_ok=True)
WINRATE_FILE = os.path.join(DATA_DIR, "winrate_history.json")

# 股票池
POOL_SIZE = 300          # 全A按流通市值取前N
KLINE_LEN = 300          # 个股K线长度
MIN_KLINE = 60           # 有效K线最低要求

# 因子与闸门(复合情绪, 三条件全过才出信号)
MOM_WINDOW = 20          # 动量回看窗口(日)
TOP_N = 20               # 每日输出股票数
GATE_MA = 10             # 指数均线闸门
BREADTH_TH = 0.55        # 市场宽度闸门: 池内当日收涨家数占比阈值
ZT_COUNT_TH = 8          # 涨停家数闸门: 池内当日涨停股数量阈值(严格>)
INDEX_LEN = 300          # 指数K线长度(新浪上限)

# 市场状态阈值(指数滚动300日收益)
BULL_TH = 0.20           # >+20% 牛市
BEAR_TH = -0.10          # <-10% 熊市(闸门强制关闭)

# 回测校准基准(实盘对账满5天后自动用实测值替换)
BT_WINRATE = 0.93        # 回测胜率(复合情绪闸门严格档)
BT_AVG_RET = 2.14        # 回测日均收益%
CALIBRATE_MIN_DAYS = 5   # 最少对账天数后启用实测校准

# 涨跌停阈值(用于风险提示标注)
LIMIT_MAIN = 9.5         # 主板
LIMIT_CYB = 19.5         # 创业板/科创板
