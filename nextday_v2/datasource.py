# -*- coding: utf-8 -*-
"""nextday_v2 数据源层
个股K线: 腾讯fqkline(前复权)   指数K线: 新浪   股票池: 腾讯全A排行(流通市值top300)
坑点备忘:
  1. 东财push2his接口高频拉取会被限流(RemoteDisconnected), 不作主源
  2. 腾讯fqkline对指数代码返回501, 指数必须走新浪
  3. 新浪datalen上限约300根
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


class DataError(RuntimeError):
    """数据获取失败(网络/源异常)"""


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))


def get_json(url, tries=3):
    last = None
    for i in range(tries):
        try:
            return _get(url)
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    raise DataError(f"请求失败 {url[:80]}: {last}")


def fetch_pool(topn=300):
    """腾讯全A排行分页拉取, 按流通市值降序取topn -> [(code, name, ltsz亿),...]"""
    items = {}
    for off in range(0, 6000, 200):
        url = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
               f"?board_code=aStock&sort_type=PriceRatio&direct=down&offset={off}&count=200")
        try:
            d = get_json(url)
        except DataError:
            break
        rl = (d.get("data") or {}).get("rank_list") or []
        if not rl:
            break
        for r in rl:
            try:
                ltsz = float(r.get("ltsz") or 0)
            except Exception:
                ltsz = 0.0
            items[r["code"]] = (r.get("name", ""), ltsz)
        time.sleep(0.12)
    if len(items) < 500:
        raise DataError(f"排行拉取失败: 仅{len(items)}条")
    ranked = sorted(items.items(), key=lambda kv: -kv[1][1])
    return [(c, nm, ltsz) for c, (nm, ltsz) in ranked[:topn]]


def fetch_kline(code, n=300):
    """前复权日线 -> [[date, close, volume],...] 升序
    主源腾讯fqkline(前复权), 失败兜底新浪(不复权, 短线场景差异可忽略)"""
    try:
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq"
        d = get_json(url, tries=2)
        node = d["data"][code]
        rows = node.get("qfqday") or node.get("day") or []
        out = []
        for r in rows:
            if len(r) < 6:
                continue
            try:
                out.append([r[0], float(r[2]), float(r[5])])
            except Exception:
                continue
        if out:
            return out
    except Exception:
        pass
    # 兜底: 新浪
    url2 = ("https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
            f"?symbol={code}&scale=240&ma=no&datalen={n}")
    d2 = get_json(url2)
    return [[r["day"], float(r["close"]), float(r["volume"])] for r in d2]


def fetch_klines(codes, n=300, workers=6, min_len=60):
    """并行拉个股K线 -> {code: rows}, 失败/过短的丢弃"""
    out = {}

    def one(code):
        try:
            rows = fetch_kline(code, n)
            return code, rows if len(rows) >= min_len else None
        except Exception:
            return code, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for code, rows in ex.map(one, codes):
            if rows:
                out[code] = rows
            time.sleep(0.03)
    return out


def fetch_index(n=300):
    """新浪上证指数日线 -> [[date, close],...] 升序"""
    url = ("https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
           f"?symbol=sh000001&scale=240&ma=no&datalen={n}")
    d = get_json(url)
    return [[r["day"], float(r["close"])] for r in d]
