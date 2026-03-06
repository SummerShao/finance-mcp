"""
A股数据服务 - 大盘概览 + 实时排行 + 实时资金流
工具: get_market_overview, get_realtime_list_top, get_realtime_moneyflow

数据源:
  - push2.eastmoney.com (指数行情 + 实时资金流 fflow)
  - 新浪财经 (全市场排行)
"""
import asyncio
import logging
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EastMoneyService:
    """东方财富数据服务（大盘概览 + 排行榜 + 实时资金流）"""

    _ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    _FFLOW_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"

    _INDEX_SECIDS = {
        "上证指数": "1.000001",
        "深证成指": "0.399001",
        "创业板指": "0.399006",
        "沪深300": "1.000300",
        "上证50": "1.000016",
        "中证500": "1.000905",
        "中证1000": "1.000852",
        "科创50": "1.000688",
    }
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/",
    }

    # ── Tool: get_market_overview ─────────────────────────────────────────────

    def _fetch_indices(self) -> Optional[List[Dict]]:
        """同步请求主要指数实时数据"""
        secids = ",".join(self._INDEX_SECIDS.values())
        try:
            resp = requests.get(
                self._ULIST_URL,
                params={
                    "fltt": "2",
                    "secids": secids,
                    "fields": "f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f104,f105,f106",
                },
                headers=self._HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
            return body.get("data", {}).get("diff")
        except Exception as e:
            logger.warning(f"EastMoney index API failed: {e}")
            return None

    async def get_market_overview(self) -> Dict[str, Any]:
        """获取A股大盘实时概览（主要指数 + 涨跌家数）"""
        loop = asyncio.get_running_loop()
        raw_list = await loop.run_in_executor(None, self._fetch_indices)
        if not raw_list:
            return {"success": False, "error": "获取指数数据失败"}

        def yi(val):
            if val is None:
                return None
            return round(val / 1e8, 2)

        indices = []
        market_stats = {}
        for item in raw_list:
            name = item.get("f14", "")
            record = {
                "name": name,
                "code": item.get("f12"),
                "price": item.get("f2"),
                "change_pct": item.get("f3"),
                "change": item.get("f4"),
                "volume_wan": round(item["f5"] / 10000, 2) if item.get("f5") else None,
                "amount_yi": yi(item.get("f6")),
                "amplitude": item.get("f7"),
                "turnover": item.get("f8"),
                "up_count": item.get("f104"),
                "down_count": item.get("f105"),
                "flat_count": item.get("f106"),
            }
            indices.append(record)

            if name == "上证指数":
                market_stats["sh_up"] = item.get("f104")
                market_stats["sh_down"] = item.get("f105")
                market_stats["sh_flat"] = item.get("f106")
            elif name == "深证成指":
                market_stats["sz_up"] = item.get("f104")
                market_stats["sz_down"] = item.get("f105")
                market_stats["sz_flat"] = item.get("f106")

        total_up = (market_stats.get("sh_up") or 0) + (market_stats.get("sz_up") or 0)
        total_down = (market_stats.get("sh_down") or 0) + (market_stats.get("sz_down") or 0)
        total_flat = (market_stats.get("sh_flat") or 0) + (market_stats.get("sz_flat") or 0)

        return {
            "success": True,
            "data": {
                "indices": indices,
                "market_stats": {
                    "total_up": total_up,
                    "total_down": total_down,
                    "total_flat": total_flat,
                    "up_down_ratio": round(total_up / total_down, 2) if total_down else None,
                },
            },
            "metadata": {
                "source": "eastmoney",
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

    # ── Tool: get_realtime_moneyflow ─────────────────────────────────────────

    def _fetch_fflow(self, secid: str) -> Optional[str]:
        """同步请求个股实时资金流（当日）"""
        try:
            resp = requests.get(
                self._FFLOW_URL,
                params={
                    "secid": secid,
                    "fields1": "f1,f2,f3",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64",
                    "lmt": "1",
                },
                headers=self._HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            klines = data.get("klines", [])
            return klines[-1] if klines else None
        except Exception as e:
            logger.warning(f"EastMoney fflow failed for {secid}: {e}")
            return None

    @staticmethod
    def _parse_fflow(kline: str, secid: str, name: str) -> Dict[str, Any]:
        """解析 fflow daykline 数据行"""
        parts = kline.split(",")
        # f51=日期 f52=主力净额 f53=小单净额 f54=中单净额 f55=大单净额 f56=超大单净额
        # f57=主力净占比% f58=小单净占比% f59=中单净占比% f60=大单净占比% f61=超大单净占比%
        # f62=收盘价 f63=涨跌幅% f64=未知
        def wan(idx: int) -> Optional[float]:
            try:
                return round(float(parts[idx]) / 10000, 2)
            except (IndexError, ValueError):
                return None

        def pct(idx: int) -> Optional[float]:
            try:
                return float(parts[idx])
            except (IndexError, ValueError):
                return None

        return {
            "secid": secid,
            "name": name,
            "trade_date": parts[0] if parts else None,
            "price": pct(11),
            "change_pct": pct(12),
            "summary": {
                "main_net_inflow_wan": wan(1),
                "main_net_pct": pct(6),
            },
            "detail": {
                "super_large": {"net_wan": wan(5), "net_pct": pct(10)},
                "large": {"net_wan": wan(4), "net_pct": pct(9)},
                "medium": {"net_wan": wan(3), "net_pct": pct(8)},
                "small": {"net_wan": wan(2), "net_pct": pct(7)},
            },
        }

    async def get_realtime_moneyflow(self, secid_name_pairs: List[tuple]) -> Dict[str, Any]:
        """
        获取A股个股实时资金流向（盘中实时数据）

        Args:
            secid_name_pairs: [(secid, name), ...] 列表
        """
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(None, self._fetch_fflow, secid)
            for secid, _ in secid_name_pairs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        records = []
        for (secid, name), raw in zip(secid_name_pairs, results):
            if isinstance(raw, Exception) or raw is None:
                continue
            records.append(self._parse_fflow(raw, secid, name))

        return {
            "success": True,
            "data": records,
            "metadata": {
                "count": len(records),
                "source": "eastmoney_fflow",
                "note": "盘中实时资金流 (交易时段实时更新，非交易时段为最近交易日数据)",
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

    # ── Tool: get_realtime_list_top ───────────────────────────────────────────

    _SINA_RANK_URL = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
        "json_v2.php/Market_Center.getHQNodeData"
    )

    _SORT_FIELD_MAP_SINA = {
        "pct_change": "changepercent",
        "amount": "amount",
        "volume": "volume",
        "turnover_rate": "turnoverratio",
        "pe": "per",
        "pb": "pb",
        "total_mv": "mktcap",
        "vol_ratio": "changepercent",
        "amplitude": "changepercent",
        "rise_speed": "changepercent",
        "main_net_inflow": "changepercent",
    }

    def _fetch_ranking_sina(self, sort_field: str, ascending: bool, pz: int) -> Optional[List[Dict]]:
        """通过新浪财经 API 获取全市场排行"""
        try:
            resp = requests.get(
                self._SINA_RANK_URL,
                params={
                    "page": "1",
                    "num": str(pz),
                    "sort": sort_field,
                    "asc": "1" if ascending else "0",
                    "node": "hs_a",
                    "symbol": "",
                    "_s_r_a": "init",
                },
                headers=self._HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Sina ranking API failed: {e}")
            return None

    async def get_realtime_list_top(
        self,
        top_n: int = 20,
        sort_by: str = "pct_change",
        ascending: bool = False,
    ) -> Dict[str, Any]:
        """获取A股全市场实时排行榜"""
        sort_field = self._SORT_FIELD_MAP_SINA.get(sort_by, "changepercent")

        loop = asyncio.get_running_loop()
        raw_list = await loop.run_in_executor(
            None, self._fetch_ranking_sina, sort_field, ascending, top_n,
        )
        if not raw_list:
            return {"success": False, "error": "获取排行数据失败"}

        def safe_float(val):
            if val is None or val == "" or val == "-":
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        records = []
        for item in raw_list:
            price = safe_float(item.get("trade"))
            pre_close = safe_float(item.get("settlement"))
            high = safe_float(item.get("high"))
            low = safe_float(item.get("low"))
            amount_raw = safe_float(item.get("amount"))
            mktcap = safe_float(item.get("mktcap"))
            nmc = safe_float(item.get("nmc"))

            amplitude = None
            if high is not None and low is not None and pre_close and pre_close > 0:
                amplitude = round((high - low) / pre_close * 100, 2)

            record = {
                "code": item.get("code"),
                "name": item.get("name"),
                "price": price,
                "pct_change": safe_float(item.get("changepercent")),
                "change": safe_float(item.get("pricechange")),
                "volume": safe_float(item.get("volume")),
                "amount": round(amount_raw / 1e4, 2) if amount_raw is not None else None,
                "amplitude": amplitude,
                "turnover_rate": safe_float(item.get("turnoverratio")),
                "pe": safe_float(item.get("per")),
                "pb": safe_float(item.get("pb")),
                "high": high,
                "low": low,
                "open": safe_float(item.get("open")),
                "pre_close": pre_close,
                "total_mv": round(mktcap / 1e4, 2) if mktcap is not None else None,
                "circ_mv": round(nmc / 1e4, 2) if nmc is not None else None,
            }
            records.append(record)

        return {
            "success": True,
            "data": records,
            "metadata": {
                "source": "sina_finance",
                "top_n": top_n,
                "sort_by": sort_by,
                "ascending": ascending,
                "count": len(records),
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
