"""
百度股市通 (FinScope) 股票数据服务（opendata 接口）
工具: get_baidu_stock_quote (capital/finance/company/news tabs)

数据源:
  - gushitong.baidu.com/opendata — 资金流向、财务、公司信息、资讯 (免费, 无需 API Key)

注: quote tab 已迁移至 Tushare 实时行情，本模块仅负责 opendata 相关 tab。
"""
import asyncio
import logging
import requests
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# tab 名称映射到 opendata 返回的 tabs 索引
_TAB_INDEX = {
    "capital": 0,    # 资金
    "news": 1,       # 资讯
    "research": 2,   # 研报/评论
    "expert": 3,     # 专家/分析
    "finance": 4,    # 财务
    "company": 5,    # 公司
}


class BaiduStockService:
    """百度股市通 opendata 数据服务"""

    _OPENDATA_URL = "https://gushitong.baidu.com/opendata"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://gushitong.baidu.com/",
        "Origin": "https://gushitong.baidu.com",
    }

    # ── HTTP fetcher ────────────────────────────────────────────────────────

    def _fetch_opendata(self, code: str) -> Optional[Dict]:
        """全量数据 (opendata) — 包含资金、财务、公司等 tab"""
        params = {
            "openapi": "1",
            "dspName": "iphone",
            "tn": "tangram",
            "client": "app",
            "query": code,
            "code": code,
            "word": code,
            "resource_id": "5429",
            "ma_ver": "4",
            "finClientType": "pc",
        }
        try:
            resp = requests.get(self._OPENDATA_URL, params=params,
                                headers=self._HEADERS, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Baidu opendata failed for {code}: {e}")
            return None

    # ── Tab parsers ─────────────────────────────────────────────────────────

    @staticmethod
    def _extract_tab_content(raw: Dict, tab_index: int) -> Optional[Dict]:
        """从 opendata 返回中提取指定 tab 的 content"""
        results = raw.get("Result", [])
        if not isinstance(results, list):
            return None
        for item in results:
            dd = item.get("DisplayData", {}).get("resultData", {}).get("tplData", {})
            tabs = dd.get("result", {}).get("tabs")
            if tabs and isinstance(tabs, list) and len(tabs) > tab_index:
                return tabs[tab_index].get("content", {})
        return None

    @staticmethod
    def _parse_capital(content: Dict) -> Dict:
        """解析资金 tab"""
        result: Dict[str, Any] = {}

        day = content.get("fundFlowDay", {}).get("result", {})
        if day:
            main = day.get("main", [])
            retail = day.get("retail", [])
            result["daily"] = {
                "unit": content.get("fundFlowDay", {}).get("unit", "亿元"),
                "main": main[-10:] if len(main) > 10 else main,
                "retail": retail[-10:] if len(retail) > 10 else retail,
            }

        spread = content.get("fundFlowSpread", {}).get("result", {})
        if spread:
            result["spread"] = {
                "super_large": spread.get("super_grp"),
                "large": spread.get("large_grp"),
                "medium": spread.get("medium_grp"),
                "small": spread.get("little_grp"),
                "total_in": spread.get("turnover_in_total"),
                "total_out": spread.get("turnover_out_total"),
                "unit": content.get("fundFlowSpread", {}).get("unit", "亿元"),
            }

        minute = content.get("fundFlowMinute", {}).get("result", {})
        if minute:
            main_m = minute.get("main", [])
            result["minute"] = {
                "unit": content.get("fundFlowMinute", {}).get("unit", "亿元"),
                "main": main_m[-20:] if len(main_m) > 20 else main_m,
            }

        return result

    @staticmethod
    def _parse_finance(content: Dict) -> Dict:
        """解析财务 tab"""
        result: Dict[str, Any] = {}

        main_sheet = content.get("mainSheet", {})
        charts = main_sheet.get("chartInfo", [])
        if charts:
            c = charts[0]
            headers = c.get("header", [])
            body = c.get("body", [])
            result["key_metrics"] = {
                "headers": ["period"] + headers + [f"{h}_yoy" for h in headers],
                "data": body[-5:] if len(body) > 5 else body,
            }

        ps = content.get("profitSheet", {})
        ps_chart = ps.get("chartInfo", [])
        if ps_chart:
            result["profit"] = {
                "headers": ["period"] + ps_chart[0].get("header", []),
                "data": ps_chart[0].get("body", []),
            }

        bs = content.get("balanceSheet", {})
        bs_chart = bs.get("chartInfo", [])
        if bs_chart:
            result["balance"] = {
                "headers": ["period"] + bs_chart[0].get("header", []),
                "data": bs_chart[0].get("body", []),
            }

        cf = content.get("cashFlowSheet", {})
        cf_chart = cf.get("chartInfo", [])
        if cf_chart:
            result["cashflow"] = {
                "headers": ["period"] + cf_chart[0].get("header", []),
                "data": cf_chart[0].get("body", []),
            }

        comp = content.get("components", {})
        comp_list = comp.get("list", [])
        if comp_list:
            result["components"] = []
            for item in comp_list[:2]:
                result["components"].append({
                    "period": item.get("title"),
                    "headers": item.get("header", []),
                    "data": item.get("body", []),
                })

        vd = content.get("valuationData", {})
        vd_charts = vd.get("chartInfo", [])
        if vd_charts:
            latest_vals = {}
            for vc in vd_charts:
                name = vc.get("header", [""])[0]
                body = vc.get("body", [])
                if body:
                    latest_vals[name] = body[-1]
            if latest_vals:
                result["valuation_latest"] = latest_vals

        return result

    @staticmethod
    def _parse_company(content: Dict) -> Dict:
        """解析公司 tab"""
        result: Dict[str, Any] = {}

        nc = content.get("newCompany", {})
        basic = nc.get("basicInfo", {})

        if basic:
            result["name"] = basic.get("companyName")
            result["release_date"] = basic.get("releaseDate")
            result["region"] = basic.get("region")
            result["industry"] = [i.get("text") if isinstance(i, dict) else i
                                  for i in basic.get("industry", [])]
            result["concepts"] = [c.get("text") if isinstance(c, dict) else c
                                  for c in basic.get("concepts", [])]
            result["area"] = [a.get("text") if isinstance(a, dict) else a
                              for a in basic.get("area", [])]
            if basic.get("mainBusiness"):
                result["main_business"] = basic["mainBusiness"]

        sh = nc.get("shareholderEquity", {})
        if sh.get("info"):
            result["shareholder"] = {
                item.get("text"): (item["value"].get("sum", item["value"])
                                   if isinstance(item.get("value"), dict) else item.get("value"))
                for item in sh["info"] if item.get("text")
            }

        rating = nc.get("organRating", {})
        if rating.get("body"):
            result["ratings"] = {
                "avg_target": rating.get("avgPrice"),
                "list": [{
                    "organ": r.get("organ"),
                    "date": r.get("date"),
                    "rating": r.get("rating"),
                    "target_price": r.get("price"),
                } for r in rating["body"]],
            }

        exec_info = nc.get("executiveInfo", {})
        if exec_info.get("body"):
            result["executives"] = [{
                "name": e.get("executive"),
                "post": e.get("post"),
                "shares": e.get("holdingCapital"),
            } for e in exec_info["body"][:10]]

        bonus = nc.get("bonusTransfer", {})
        if bonus.get("body"):
            result["dividends"] = [{
                "date": b[0],
                "plan": b[1],
                "ex_date": b[2],
            } for b in bonus["body"][:5] if isinstance(b, list) and len(b) >= 3]

        return result

    @staticmethod
    def _parse_news(content: Dict) -> List[Dict]:
        """解析资讯 tab — 返回最近新闻列表"""
        news_items = []
        for key in ("news", "fastNews", "tradeNews", "reportNews", "noticeNews"):
            items = content.get(key)
            if isinstance(items, list):
                for item in items[:5]:
                    entry: Dict[str, Any] = {"type": key}
                    if isinstance(item, dict):
                        entry["title"] = item.get("title", item.get("content", ""))
                        entry["time"] = item.get("publishTime", item.get("time", ""))
                        entry["source"] = item.get("source", "")
                        if item.get("url"):
                            entry["url"] = item["url"]
                    news_items.append(entry)
        return news_items[:20]

    # ── Public method ───────────────────────────────────────────────────────

    async def get_stock_quote(self, stock_input: str, tab: str = "quote") -> Dict[str, Any]:
        """
        获取百度股市通 opendata 数据（capital/finance/company/news）

        Args:
            stock_input: 股票代码（6位数字）
            tab: 数据类型 — 'capital'/'finance'/'company'/'news'
        """
        # 从输入中提取代码
        code = stock_input.strip()
        if "gushitong.baidu.com" in code:
            import re
            m = re.search(r"ab-(\w+)", code)
            code = m.group(1) if m else code

        tab_index = _TAB_INDEX.get(tab)
        if tab_index is None:
            return {"success": False, "error": f"未知 tab: {tab}，可选: capital/finance/company/news"}

        meta = {
            "source": "baidu_opendata",
            "tab": tab,
            "url": f"https://gushitong.baidu.com/stock/ab-{code}",
        }

        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._fetch_opendata, code)
        if not raw:
            return {"success": False, "error": f"百度股市通 opendata 未返回数据: {code}"}

        content = self._extract_tab_content(raw, tab_index)
        if not content:
            return {"success": False, "error": f"未找到 tab '{tab}' 的数据"}

        if tab == "capital":
            parsed = self._parse_capital(content)
        elif tab == "finance":
            parsed = self._parse_finance(content)
        elif tab == "company":
            parsed = self._parse_company(content)
        elif tab == "news":
            parsed = self._parse_news(content)
        else:
            parsed = content

        return {"success": True, "data": parsed, "metadata": meta}
