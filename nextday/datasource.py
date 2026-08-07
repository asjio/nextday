# -*- coding: utf-8 -*-
"""数据源层 -- 移植点。
换市场/品种只需重写本文件, 对外暴露三个函数:
  snapshot()        -> {code: 快照dict} 全市场当日快照
  kline(code, n)    -> [[date, open, close, high, low, volume], ...] 前复权日线
  is_trading_day(d) -> bool
当前实现: 腾讯财经 (A股)。
"""
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
RANK_BASE = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
             "?board_code=aStock&sort_type=PriceRatio&direct=down")


def _fetch_json(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))


class DataError(RuntimeError):
    """数据获取失败(网络/源异常), 区别于"非交易日"等业务性跳过"""


def snapshot(max_workers=8, retries=3):
    """全市场当日快照: {code(如sz300248): 原始字段dict}。失败重试, 全失败抛DataError"""
    import time
    last_err = None
    for att in range(retries):
        items = {}
        errs = 0

        def pull(off):
            nonlocal errs
            try:
                d = _fetch_json(RANK_BASE + f"&offset={off}&count=200")
                return (d.get("data") or {}).get("rank_list") or []
            except Exception:
                errs += 1
                return []

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for lst in ex.map(pull, list(range(0, 6000, 200))):
                for r in lst:
                    items[r["code"]] = r
        if len(items) >= 500:
            return items
        last_err = f"仅获取{len(items)}条(分页失败{errs}次)"
        time.sleep(2 * (att + 1))
    raise DataError(f"快照获取失败: {last_err}, 疑似网络被墙, 稍后重试")


_last_date_cache = {}


def last_trade_date():
    """最近一个交易日日期(上证指数最后一根K线)"""
    rows = kline("sh000001", 20)
    return rows[-1][0]


def next_trading_date(after_date):
    """after_date之后第一个交易日。
    已过去的日期查K线; 未来日期用日历推算(跳过周末, 法定节假日无法预知, 前端标注)"""
    if after_date in _last_date_cache:
        return _last_date_cache[after_date]
    # 先查K线(适用于对账场景)
    try:
        rows = kline("sh000001", 40)
        for r in rows:
            if r[0] > after_date:
                _last_date_cache[after_date] = r[0]
                return r[0]
    except Exception:
        pass
    # 未来日期: 日历推算下一个工作日
    import datetime as _dt
    d = _dt.date.fromisoformat(after_date)
    for _ in range(10):
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            _last_date_cache[after_date] = d.isoformat()
            return d.isoformat()
    return None


def kline(code, n=640):
    """前复权日线: [[date, open, close, high, low, volume], ...] 升序"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq"
    d = _fetch_json(url)
    node = d["data"][code]
    rows = node.get("qfqday") or node.get("day") or []
    return [r[:6] for r in rows if len(r) >= 6]


def is_trading_day(date_str):
    """用上证指数K线判断某日是否交易日"""
    try:
        rows = kline("sh000001", 30)
        return date_str in {r[0] for r in rows}
    except Exception:
        return False


def full_code(code6):
    """6位代码 -> 带前缀"""
    return ("sh" if code6.startswith("6") else "sz") + code6
