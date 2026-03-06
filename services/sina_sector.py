"""
A股板块涨跌幅排行服务 - 基于新浪财经
工具: get_sector_ranking

数据源:
  - vip.stock.finance.sina.com.cn — 行业板块 (免费, 无需 API Key)
  - money.finance.sina.com.cn     — 概念板块 (免费, 无需 API Key)
"""
import re
import asyncio
import logging
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SinaSectorService:
    """新浪财经板块涨跌排行服务"""

    _INDUSTRY_URL = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
    _CONCEPT_URL = "https://money.finance.sina.com.cn/q/view/newFLJK.php?param=class"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.sina.com.cn/",
    }

    # JS 变量名 -> URL 映射
    _VAR_MAP = {
        "industry": "S_Finance_bankuai_sinaindustry",
        "concept": "S_Finance_bankuai_class",
    }

    # ── HTTP fetchers ─────────────────────────────────────────────────────────

    def _fetch_raw(self, url: str) -> Optional[str]:
        """同步请求新浪板块数据（返回原始 JS 文本）"""
        try:
            resp = requests.get(url, headers=self._HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = "gbk"
            return resp.text
        except Exception as e:
            logger.warning(f"Sina sector API failed for {url}: {e}")
            return None

    # ── Parser ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_sectors(text: str, var_name: str) -> List[Dict[str, Any]]:
        """
        解析新浪返回的 JS 变量。

        格式: var xxx = {"key":"code,名称,个股数,均价,涨跌额,涨跌幅%,volume,amount,
                          领涨code,领涨涨幅%,领涨价格,领涨涨跌额,领涨名称", ...}
        """
        match = re.search(r"var\s+" + var_name + r"\s*=\s*\{(.+)\}", text, re.DOTALL)
        if not match:
            return []

        sectors: List[Dict[str, Any]] = []
        for item in re.findall(r'"([^"]+)":"([^"]+)"', match.group(1)):
            fields = item[1].split(",")
            if len(fields) < 6:
                continue

            name = fields[1]
            stock_count = int(fields[2]) if fields[2].isdigit() else 0

            try:
                change_pct = float(fields[5])
            except (ValueError, IndexError):
                change_pct = 0.0

            try:
                avg_price = float(fields[3])
            except (ValueError, IndexError):
                avg_price = 0.0

            try:
                change = float(fields[4])
            except (ValueError, IndexError):
                change = 0.0

            # 领涨股信息（字段 8~12）
            leader_name = fields[-1] if len(fields) > 10 else ""
            try:
                leader_pct = float(fields[-4]) if len(fields) > 10 else 0.0
            except (ValueError, IndexError):
                leader_pct = 0.0

            try:
                leader_price = float(fields[-3]) if len(fields) > 10 else 0.0
            except (ValueError, IndexError):
                leader_price = 0.0

            sectors.append({
                "name": name,
                "stock_count": stock_count,
                "avg_price": avg_price,
                "change": round(change, 4),
                "change_pct": round(change_pct, 2),
                "leader": {
                    "name": leader_name,
                    "change_pct": round(leader_pct, 2),
                    "price": leader_price,
                },
            })

        # 按涨跌幅降序
        sectors.sort(key=lambda x: x["change_pct"], reverse=True)
        return sectors

    # ── Public method ─────────────────────────────────────────────────────────

    async def get_sector_ranking(
        self,
        sector_type: str = "industry",
        top_n: int = 30,
    ) -> Dict[str, Any]:
        """
        获取A股板块涨跌幅排行

        Args:
            sector_type: 'industry'(行业板块) 或 'concept'(概念板块)
            top_n: 返回前N个板块（按涨幅降序），默认30
        """
        if sector_type not in ("industry", "concept"):
            return {"success": False, "error": f"未知板块类型: {sector_type}，可选: industry/concept"}

        url = self._INDUSTRY_URL if sector_type == "industry" else self._CONCEPT_URL
        var_name = self._VAR_MAP[sector_type]

        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._fetch_raw, url)
        if not raw:
            return {"success": False, "error": f"获取{sector_type}板块数据失败"}

        sectors = self._parse_sectors(raw, var_name)
        if not sectors:
            return {"success": False, "error": "解析板块数据失败"}

        total = len(sectors)
        up_count = sum(1 for s in sectors if s["change_pct"] > 0)
        down_count = sum(1 for s in sectors if s["change_pct"] < 0)
        flat_count = total - up_count - down_count

        # 截取 top_n
        top = sectors[:top_n] if top_n < total else sectors
        bottom_n = min(5, total)
        bottom = sectors[-bottom_n:] if top_n < total else []

        type_label = "行业板块" if sector_type == "industry" else "概念板块"
        data: Dict[str, Any] = {
            "type": type_label,
            "total_sectors": total,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "top": top,
        }
        if bottom:
            data["bottom"] = bottom

        return {
            "success": True,
            "data": data,
            "metadata": {
                "source": "sina_finance",
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
