# -*- coding: utf-8 -*-
"""nextday_v2 配置
策略: 动量20日选股 + 防守闸门(指数MA10 + 市场宽度55%)
回测依据(2025.4~2026.8, 全A流通市值前300, walk-forward, 次日持有Top20):
  闸门=指数>MA10且池内上涨家数占比>55%:
  信号日68天, 胜率69%, 日均涨+0.97%, 累计+89.3%, 最差单日-4.08%, 亏损日仅21天
设计目标: 不亏优先。防守代价是约2/3交易日空仓(市场不好不参与)。
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

# 因子与闸门
MOM_WINDOW = 20          # 动量回看窗口(日)
TOP_N = 20               # 每日输出股票数
GATE_MA = 10             # 指数均线闸门
BREADTH_TH = 0.55        # 市场宽度闸门: 池内当日收涨家数占比阈值
INDEX_LEN = 300          # 指数K线长度(新浪上限)

# 市场状态阈值(指数滚动300日收益)
BULL_TH = 0.20           # >+20% 牛市
BEAR_TH = -0.10          # <-10% 熊市(闸门强制关闭)

# 回测校准基准(实盘对账满5天后自动用实测值替换)
BT_WINRATE = 0.69        # 回测胜率(MA10+宽度55%闸门, 次日持有Top20)
BT_AVG_RET = 0.97        # 回测日均收益%
CALIBRATE_MIN_DAYS = 5   # 最少对账天数后启用实测校准

# 涨跌停阈值(用于风险提示标注)
LIMIT_MAIN = 9.5         # 主板
LIMIT_CYB = 19.5         # 创业板/科创板
