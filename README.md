# NextDay - 次日涨跌概率预测模型

历史相似日KNN模型: 用2.5年真实日线构建11万+样本库, 对当日强势股打分,
输出"明日上涨概率", 次日收盘自动对账, 累积真实胜率曲线。

## 原理
1. 特征: 当日涨幅/5-20-60日动量/60日位置/量能比/大阳标记 (7维)
2. 建库: 每只股票每个交易日提取特征, 配对次日真实收益
3. 预测: 找历史上最相似的60个交易日, 统计次日收益分布
4. 验证: 次日收盘对账, 记录命中率, 画胜率曲线

## 运行
- 双击 `run_daily.bat` 即可
- 或: `.venv\Scripts\python.exe -m nextday.main`
- 定时任务: Hermes cron 每交易日15:30自动执行

## 移植到其他市场
只需重写 `nextday/datasource.py` 的三个函数:
- `snapshot()` -> 全市场快照
- `kline(code, n)` -> 前复权日线 [[date,o,c,h,l,v],...]
- `is_trading_day(date)` -> bool
特征/模型/验证/报告层与市场无关, 不用改。

## 数据文件
- `data/predictions/pred_YYYY-MM-DD.json` 每日预测存档
- `data/predictions/detail_YYYY-MM-DD.json` 对账明细
- `data/winrate_history.json` 胜率累积记录
- `data/reports/winrate_curve.png` 胜率曲线图

## 已知坑
1. PYTHONPATH污染: Hermes环境导出了PYTHONPATH指向自己的venv,
   运行时必须清空(`set PYTHONPATH=`或`PYTHONPATH=`前缀), 否则numpy版本冲突
2. venv用系统Python 3.13 (D:\Program Files\Python)创建, 与Hermes的3.11隔离
3. 周五预测的对账日是下周一, 非交易日自动跳过


## Web台账页面
- 双击 `web.bat` 启动, 自动打开 http://127.0.0.1:8766
- 功能: 累计统计/胜率曲线(ECharts)/预测台账(逐日切换,已对账显示中失印章)/页面内手动执行每日流程
- 前端: React19+Vite+Tailwind4+ECharts, 账本宣纸风, 构建产物 frontend/dist
- API: /api/overview /api/winrate /api/predictions/dates /api/predictions/{date} /api/run /api/run_status
- 开发模式: cd frontend && npm run dev (代理/api到8766)
