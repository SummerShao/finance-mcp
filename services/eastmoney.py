"""
A股实时资金流向服务 - 基于东方财富 HTTP API
工具: get_realtime_moneyflow

数据源: push2.eastmoney.com (免费, 无需 API Key)
资金分级: 小单 ≤ 5万 | 中单 5~20万 | 大单 20~100万 | 超大单 ≥ 100万
"""
import time
import asyncio
import logging
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EastMoneyService:
    """东方财富实时资金流向服务"""

    _API_URL = "https://push2.eastmoney.com/api/qt/stock/get"
    _FIELDS = "f57,f58,f135,f136,f137,f138,f139,f140,f141,f142,f143,f144,f145,f146,f147,f148,f149"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/",
    }
    _CACHE_TTL = 60  # 60 秒内存缓存

    def __init__(self, tushare_svc):
        self._tushare = tushare_svc
        self._cache: Dict[str, tuple] = {}  # key -> (timestamp, data)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _ts_code_to_secid(ts_code: str) -> str:
        """'002155.SZ' -> '0.002155', '600519.SH' -> '1.600519'"""
        code, exchange = ts_code.split(".")
        market = "1" if exchange == "SH" else "0"
        return f"{market}.{code}"

    def _get_cached(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry and (time.time() - entry[0]) < self._CACHE_TTL:
            return entry[1]
        return None

    def _set_cache(self, key: str, data: Any):
        self._cache[key] = (time.time(), data)

    def _http_get_one(self, secid: str) -> Optional[Dict]:
        """同步请求单只股票的实时资金流向"""
        try:
            resp = requests.get(
                self._API_URL,
                params={"secid": secid, "fields": self._FIELDS},
                headers=self._HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("rc") == 0 and body.get("data"):
                return body["data"]
            return None
        except Exception as e:
            logger.warning(f"EastMoney API failed for {secid}: {e}")
            return None

    @staticmethod
    def _parse_record(raw: Dict) -> Optional[Dict]:
        """解析单只股票的 API 响应为标准格式（金额转万元）"""

        def wan(val) -> Optional[float]:
            """元 -> 万元, 保留2位"""
            if val is None or val == "" or val == "-":
                return None
            return round(float(val) / 10000, 2)

        code = raw.get("f57")
        name = raw.get("f58", "")
        if not code:
            return None

        # 四级明细
        super_large_buy = wan(raw.get("f138"))
        super_large_sell = wan(raw.get("f139"))
        super_large_net = wan(raw.get("f140"))
        large_buy = wan(raw.get("f141"))
        large_sell = wan(raw.get("f142"))
        large_net = wan(raw.get("f143"))
        medium_buy = wan(raw.get("f144"))
        medium_sell = wan(raw.get("f145"))
        medium_net = wan(raw.get("f146"))
        small_buy = wan(raw.get("f147"))
        small_sell = wan(raw.get("f148"))
        small_net = wan(raw.get("f149"))

        # 主力/散户汇总
        main_inflow = wan(raw.get("f135"))
        main_outflow = wan(raw.get("f136"))
        main_net = wan(raw.get("f137"))

        # 散户 = 中单 + 小单
        retail_inflow = None
        retail_outflow = None
        retail_net = None
        if medium_buy is not None and small_buy is not None:
            retail_inflow = round(medium_buy + small_buy, 2)
        if medium_sell is not None and small_sell is not None:
            retail_outflow = round(medium_sell + small_sell, 2)
        if medium_net is not None and small_net is not None:
            retail_net = round(medium_net + small_net, 2)

        return {
            "code": code,
            "name": name,
            "summary": {
                "main_inflow_wan": main_inflow,
                "main_outflow_wan": main_outflow,
                "main_net_inflow_wan": main_net,
                "retail_inflow_wan": retail_inflow,
                "retail_outflow_wan": retail_outflow,
                "retail_net_inflow_wan": retail_net,
            },
            "detail": {
                "super_large": {
                    "buy_wan": super_large_buy,
                    "sell_wan": super_large_sell,
                    "net_wan": super_large_net,
                },
                "large": {
                    "buy_wan": large_buy,
                    "sell_wan": large_sell,
                    "net_wan": large_net,
                },
                "medium": {
                    "buy_wan": medium_buy,
                    "sell_wan": medium_sell,
                    "net_wan": medium_net,
                },
                "small": {
                    "buy_wan": small_buy,
                    "sell_wan": small_sell,
                    "net_wan": small_net,
                },
            },
        }

    # ── Main tool method ──────────────────────────────────────────────────────

    async def get_realtime_moneyflow(self, stock_names: str) -> Dict[str, Any]:
        """获取A股个股实时资金流向（盘中实时数据，来源东方财富）"""
        names = [n.strip() for n in stock_names.split(",") if n.strip()]
        if not names:
            return {"success": False, "error": "未提供股票名称"}
        if len(names) > 50:
            return {"success": False, "error": "单次最多查询50只股票"}

        name_code = await self._tushare._names_to_codes(names)
        if not name_code:
            return {"success": False, "error": f"无法解析股票名称: {stock_names}"}

        not_found = [n for n in names if n not in name_code]

        # 分离缓存命中和需要请求的股票
        loop = asyncio.get_running_loop()
        cached_results: Dict[str, Dict] = {}
        fetch_items: List[tuple] = []  # (ts_code, secid)

        for ts_code in name_code.values():
            secid = self._ts_code_to_secid(ts_code)
            cached = self._get_cached(secid)
            if cached is not None:
                cached_results[ts_code] = cached
            else:
                fetch_items.append((ts_code, secid))

        # 并行请求未缓存的股票
        if fetch_items:
            fetch_tasks = [
                loop.run_in_executor(None, self._http_get_one, secid)
                for _, secid in fetch_items
            ]
            fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            for (ts_code, secid), raw in zip(fetch_items, fetch_results):
                if not isinstance(raw, Exception) and raw is not None:
                    self._set_cache(secid, raw)
                    cached_results[ts_code] = raw

        # 解析所有结果
        records = []
        for ts_code in name_code.values():
            raw = cached_results.get(ts_code)
            if raw:
                parsed = self._parse_record(raw)
                if parsed:
                    records.append(parsed)

        meta: Dict[str, Any] = {
            "count": len(records),
            "source": "eastmoney",
            "note": "资金分级: 小单≤5万 | 中单5~20万 | 大单20~100万 | 超大单≥100万（东方财富标准）",
            "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if not_found:
            meta["not_found"] = not_found

        return {"success": True, "data": records, "metadata": meta}
