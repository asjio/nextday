# 交接文档: nextday 项目部署到个人 VPS

> 本文档写给接手本任务的 AI 助手。用户: 尚子龙, Windows 10, 中国办公网环境。
> 编写时间: 2026-08-18, 由 Hermes Agent(办公网会话)整理, 记录已完成工作与待办。

---

## 一、背景: 要干什么

用户刚买了一台 RackNerd VPS(年付约67美元), 想把本地量化项目 nextday 部署上去,
核心诉求是: 在办公网也能打开 nextday 的 Web 台账页面(办公网拦 SSH 但不拦 HTTP)。

最终确定的部署模式: **数据搬运模式(本地计算, VPS展示)**
- 本地 Windows 机器(中国网络)继续负责: 每日拉行情数据 + 跑预测 + 对账
- VPS(美国)只负责: Web 展示台账页面
- 本地每日算完后, 把增量数据文件上传到 VPS
- 原因: nextday 的数据源是腾讯/新浪 A股接口, 从美国 IP 能否访问未经验证,
  数据搬运模式不赌这个前提, 最稳

---

## 二、nextday 项目说明

### 位置与结构
- 项目根目录: `D:\工具\nextday`
- 现行版本: `nextday_v2/`(v1 KNN 已废弃, 勿动)
- v2 模块: `main.py`(每日入口) / `engine.py`(因子计算) / `datasource.py`(数据源) /
  `validate.py`(对账) / `web.py`(FastAPI台账, 端口8767) / `config.py`(策略参数) / `backtest.py`
- 数据目录: `D:\工具\nextday\data\v2\`
  - `predictions/pred_YYYY-MM-DD.json`: 每日预测存档
  - `predictions/detail_*.json`: 对账明细
  - `winrate_history.json`: 胜率累积记录
- 前端: `frontend/`(React19+Vite+Tailwind4+ECharts), 构建产物 `frontend/dist`, web.py 直接伺服

### 策略(v2, 不亏优先)
动量20日选股 + 复合情绪闸门(指数>MA10 且 市场宽度>55% 且 池内涨停家数>8),
信号约每月1次, 回测14天胜率93%/日均+2.14%。交易语义: t日收盘出信号 -> t+1收盘买入 -> t+2收盘卖出。

### 数据源(datasource.py, 全是腾讯/新浪HTTP接口)
- 股票池: `proxy.finance.qq.com` 全A排行(流通市值top300)
- 个股K线: `web.ifzq.gtimg.cn` fqkline(前复权), 指数走该接口会501必须走新浪
- 指数K线: 新浪(datalen上限约300根)
- 东财接口会被限流, 不作主源

### 运行方式
- 手动: `D:\工具\nextday\run_v2.bat`(即 `.venv\Scripts\python.exe -m nextday_v2.main`)
- 定时: Hermes cron 工作日15:30自动执行(job id b690b0c9ff36)
- Web: `web_v2.bat` 启动 8767 端口
- 坑1: 运行时必须清空 PYTHONPATH(Hermes 环境污染会导致 numpy 版本冲突)
- 坑2: venv 用系统 Python 3.13 创建(`D:\Program Files\Python`), 与 Hermes 的 3.11 隔离

---

## 三、VPS 现状(2026-08-18 实测)

| 项目 | 值 |
|:-----|:---|
| 服务商 | RackNerd, Debian 12 |
| IP/面板/密码 | 敏感信息不入git, 见用户桌面《VPS搭建进度与回家操作清单.md》或直接问用户 |
| SSH 模式 | socket 激活(改端口必须同步改 ssh.socket) |

### 已完成的修复
1. sshd 主机密钥损坏导致无法连接 -> 已用 `ssh-keygen -A` 修复, sshd 正常
2. 已确认: 服务器对外服务正常(境外IP可完成完整SSH握手, 127.0.0.1本地登录OK, iptables全ACCEPT)

### 关键网络限制(必读)
**办公网(Citrix虚拟桌面)对SSH做深度包检测,
TCP能连但在SSH banner阶段被reset。办公网永远连不上这台VPS的SSH, 不要再排查。**
所有SSH操作必须在家庭网络/手机热点下进行。HTTP/HTTPS 不受影响。

### 安全状况(紧急)
auth.log 显示该 IP 上线1小时即遭多个境外IP持续暴力破解。
部署完成后必须: 改SSH端口(23456) + 密钥登录 + 禁root密码登录 + fail2ban。
密码曾在聊天中明文出现, 必须全部改掉(root密码 + SolusVM面板密码)。

---

## 四、待办清单(按顺序)

前提: 用户在家庭网络下, 已能 SSH 登录。

1. 安全加固(最优先)
   - 先用 `ss -tlnp | grep 23456` 确认未被占用, 再改 SSH 端口到 23456: 改 `/etc/ssh/sshd_config` 的 Port, **同步改** `/lib/systemd/system/ssh.socket`,
     然后 `systemctl daemon-reload && systemctl restart ssh.socket`
   - 操作纪律(防锁死,必须遵守): 改完端口后先用新端口 `ssh -p 23456 root@<IP>` 验证能连上,
     确认成功后才允许关闭旧的22端口监听。顺序反了会被锁在门外, 只能重新走SolusVM面板的noVNC
   - 配置密钥登录, 禁用 root 密码登录, 装 fail2ban
   - 密钥登录纪律: 公钥写入 `/root/.ssh/authorized_keys` 后, 必须先新开一个终端用密钥+新端口
     完整登录一次成功, 再改 sshd_config 禁密码登录。没验证就禁密码 = 锁死
2. 数据源可达性测试(决定是否需要数据搬运模式的兜底方案)
   ```
   curl -s -o /dev/null -w "%{http_code}" "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,5,qfq"
   ```
   返回200说明接口从美国可达; 403/超时则坚持数据搬运模式
3. VPS 环境准备
   - 装 Python3.11+, fastapi, uvicorn, numpy(仅web展示层其实只需fastapi+numpy)
   - 时区设为 Asia/Shanghai(`timedatectl set-timezone Asia/Shanghai`)
4. 部署 web 展示层
   - 上传 `nextday_v2/`(web.py/engine.py/config.py等) + `frontend/dist` + `data/v2/`
   - 用 systemd 或 nohup 跑 `python -m nextday_v2.web`(端口8767, 可改80/443)
   - 注意 web.py 的 /api/run 手动触发功能在VPS上不可用(数据源问题), 需禁用或提示
5. 编写同步脚本(数据搬运核心, 在本地 Windows 跑)
   - 每日预测跑完后, 用 scp/rsync 上传 `data/v2/` 增量到 VPS
   - 可挂到现有每日流程末尾(run_v2.bat 或 Hermes cron)
   - 每日数据量几百KB, 全量覆盖最简单可靠
6. 收尾: 开 BBR 加速(sysctl 加 net.core.default_qdisc=fq 和 net.ipv4.tcp_congestion_control=bbr)

---

## 五、相关文档
- 桌面《VPS搭建进度与回家操作清单.md》: VPS 基础搭建(SSH/3x-ui/建站)的完整清单, 本文档的部署任务在其之后进行
