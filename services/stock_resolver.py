"""
A股股票名称 ↔ 代码解析服务（免费，无需 API Key）

数据源:
  - 东方财富搜索 API (searchapi.eastmoney.com) — 主要，按需查询
  - 东方财富全量股票列表 API (push2.eastmoney.com) — 可选预加载
"""
import time
import json
import asyncio
import logging
import requests
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class StockResolver:
    """股票名称 ↔ 代码解析（基于东方财富免费 API）"""

    _LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    _SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/",
    }

    CACHE_DIR = Path("/tmp/mcp_cache/stock_resolver")
    CACHE_EXPIRE_HOURS = 12

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._name_to_info: Dict[str, dict] = {}  # name -> {code, name, market, secid}
        self._code_to_info: Dict[str, dict] = {}  # code(6位) -> {code, name, market, secid}
        self._list_loaded = False

    # ── Cache helpers ─────────────────────────────────────────────────────────

    def _load_cache(self, key: str):
        f = self.CACHE_DIR / f"{key}.json"
        if f.exists():
            try:
                d = json.loads(f.read_text())
                if time.time() - d["ts"] < self.CACHE_EXPIRE_HOURS * 3600:
                    return d["data"]
            except Exception:
                pass
        return None

    def _save_cache(self, key: str, data):
        try:
            (self.CACHE_DIR / f"{key}.json").write_text(
                json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False)
            )
        except Exception:
            pass

    def _put_info(self, info: dict):
        """将一条股票信息存入内存缓存"""
        self._name_to_info[info["name"]] = info
        self._code_to_info[info["code"]] = info

    # ── Search API (primary, per-stock) ───────────────────────────────────────

    def _search_stock(self, query: str) -> Optional[dict]:
        """
        通过东方财富搜索 API 解析单只股票（支持名称或代码）。
        返回 {code, name, market, secid} 或 None。
        """
        try:
            resp = requests.get(
                self._SEARCH_URL,
                params={
                    "input": query,
                    "type": "14",
                    "token": "D43BF722C8E33BDC906FB84D85E326E8",
                    "count": "5",
                },
                headers=self._HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            table = resp.json().get("QuotationCodeTable", {})
            data_list = table.get("Data")
            if not data_list:
                return None

            # 优先精确匹配（名称或代码完全一致）
            for item in data_list:
                if item.get("Classify") != "AStock":
                    continue
                code = item.get("Code", "")
                name = item.get("Name", "")
                if query == name or query == code:
                    mkt = int(item.get("MktNum", "0"))
                    return {
                        "code": code,
                        "name": name,
                        "market": mkt,
                        "secid": f"{mkt}.{code}",
                    }

            # 无精确匹配时取第一个 A 股结果
            for item in data_list:
                if item.get("Classify") != "AStock":
                    continue
                code = item.get("Code", "")
                name = item.get("Name", "")
                mkt = int(item.get("MktNum", "0"))
                return {
                    "code": code,
                    "name": name,
                    "market": mkt,
                    "secid": f"{mkt}.{code}",
                }

            return None
        except Exception as e:
            logger.warning(f"Search API failed for '{query}': {e}")
            return None

    # ── Full stock list (optional bulk preload) ───────────────────────────────

    def _fetch_stock_list(self) -> List[dict]:
        """从东方财富获取全 A 股列表（代码、名称、市场）"""
        cached = self._load_cache("stock_list")
        if cached:
            return cached

        all_stocks = []
        for fs_type, market_id in [("m:0+t:6,7,8", 0), ("m:1+t:2,23", 1)]:
            try:
                resp = requests.get(
                    self._LIST_URL,
                    params={
                        "pn": "1",
                        "pz": "10000",
                        "fs": fs_type,
                        "fields": "f12,f14",
                        "fid": "f12",
                    },
                    headers=self._HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                diff = data.get("diff", [])
                for item in diff:
                    code = item.get("f12", "")
                    name = item.get("f14", "")
                    if code and name:
                        all_stocks.append({
                            "code": code,
                            "name": name,
                            "market": market_id,
                            "secid": f"{market_id}.{code}",
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch stock list (fs={fs_type}): {e}")

        if all_stocks:
            self._save_cache("stock_list", all_stocks)
        return all_stocks

    async def _ensure_loaded(self):
        """尝试加载全量列表到内存（非关键路径，失败不影响单只查询）"""
        if self._list_loaded:
            return

        self._list_loaded = True  # 只尝试一次
        loop = asyncio.get_running_loop()
        try:
            stocks = await loop.run_in_executor(None, self._fetch_stock_list)
            for s in stocks:
                self._put_info(s)
        except Exception as e:
            logger.warning(f"Stock list preload failed (non-critical): {e}")

    # ── Unified resolve API ──────────────────────────────────────────────────

    @staticmethod
    def _is_code(s: str) -> bool:
        """判断是否为 6 位股票代码"""
        return len(s) == 6 and s.isdigit()

    async def resolve(self, input_str: str) -> Optional[dict]:
        """
        统一解析入口：支持股票名称或 6 位代码。
        返回 {code, name, market, secid} 或 None。

        查找顺序: 内存缓存 → 搜索 API
        """
        input_str = input_str.strip()
        if not input_str:
            return None

        # 先尝试预加载全量列表
        await self._ensure_loaded()

        # 1. 查内存缓存
        if self._is_code(input_str):
            info = self._code_to_info.get(input_str)
            if info:
                return info
        else:
            info = self._name_to_info.get(input_str)
            if info:
                return info

        # 2. 搜索 API fallback
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, self._search_stock, input_str)
        if info:
            self._put_info(info)
            return info

        return None

    async def resolve_many(self, inputs: List[str]) -> Dict[str, dict]:
        """
        批量解析。返回 {input_str: {code, name, market, secid}}。
        未找到的不包含在结果中。
        """
        # 先预加载
        await self._ensure_loaded()

        result: Dict[str, dict] = {}
        to_search: List[str] = []

        # 先查内存缓存
        for inp in inputs:
            inp = inp.strip()
            if not inp:
                continue
            if self._is_code(inp):
                info = self._code_to_info.get(inp)
            else:
                info = self._name_to_info.get(inp)

            if info:
                result[inp] = info
            else:
                to_search.append(inp)

        # 批量搜索（并发）
        if to_search:
            loop = asyncio.get_running_loop()
            tasks = [loop.run_in_executor(None, self._search_stock, q) for q in to_search]
            search_results = await asyncio.gather(*tasks, return_exceptions=True)
            for q, res in zip(to_search, search_results):
                if isinstance(res, Exception) or res is None:
                    continue
                self._put_info(res)
                result[q] = res

        return result

    # ── Legacy API (backward-compatible) ─────────────────────────────────────

    async def names_to_codes(self, names: List[str]) -> Dict[str, str]:
        """股票名称 → 6位代码。返回 {name: code}。"""
        resolved = await self.resolve_many(names)
        return {k: v["code"] for k, v in resolved.items()}

    async def names_to_secids(self, names: List[str]) -> Dict[str, str]:
        """股票名称 → 东方财富 secid（如 '1.600519'）。"""
        resolved = await self.resolve_many(names)
        return {k: v["secid"] for k, v in resolved.items()}

    async def codes_to_names(self, codes: List[str]) -> Dict[str, str]:
        """6位代码 → 股票名称。返回 {code: name}。"""
        resolved = await self.resolve_many(codes)
        return {k: v["name"] for k, v in resolved.items()}

    async def code_to_secid(self, code: str) -> Optional[str]:
        """6位代码 → secid"""
        info = await self.resolve(code)
        return info["secid"] if info else None

    @staticmethod
    def secid_from_code(code: str) -> str:
        """
        6位代码 → secid（纯规则推导，无需加载列表）。
        6开头 = 沪市(1)，其余 = 深市(0)
        """
        market = "1" if code.startswith("6") else "0"
        return f"{market}.{code}"
