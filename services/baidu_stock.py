"""
百度股市通 (FinScope) 股票行情服务
工具: get_baidu_stock_quote

数据源:
  - finance.pae.baidu.com/vapi  — 实时行情、盘口 (免费, 无需 API Key)
  - gushitong.baidu.com/opendata — 资金流向、财务、公司信息 (免费, 无需 API Key)
"""
import re
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
    """百度股市通行情服务"""

    _VAPI_URL = "https://finance.pae.baidu.com/vapi/v1/getquotation"
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

    _URL_RE = re.compile(r"gushitong\.baidu\.com/stock/(\w+)-(\w+)")

    # ── Input parsing ──────────────────────────────────────────────────────────

    @classmethod
    def _parse_url(cls, url: str) -> tuple[str, str]:
        m = cls._URL_RE.search(url)
        if m:
            return m.group(1), m.group(2)
        raise ValueError(f"无法解析百度股市通 URL: {url}")

    @classmethod
    def _detect_market(cls, code: str) -> str:
        if code.isdigit() and len(code) == 6:
            return "ab"
        if code.isalpha():
            return "us"
        return "ab"

    @classmethod
    def _resolve_input(cls, stock_input: str) -> tuple[str, str]:
        """返回 (market_type, code)"""
        if "gushitong.baidu.com" in stock_input:
            return cls._parse_url(stock_input)
        code = stock_input.strip()
        return cls._detect_market(code), code

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        if val is None or val == "" or val == "-" or val == "--":
            return None
        try:
            return float(str(val).replace(",", "").replace("%", ""))
        except (ValueError, TypeError):
            return None

    # ── HTTP fetchers ──────────────────────────────────────────────────────────

    def _fetch_vapi(self, market_type: str, code: str) -> Optional[Dict]:
        """实时行情 (vapi)"""
        params = {
            "srcid": "5353",
            "pointType": "string",
            "group": f"quotation_minute_{market_type}",
            "query": code,
            "code": code,
            "market_type": market_type,
            "newFormat": "1",
            "is_498": "1",
        }
        try:
            resp = requests.get(self._VAPI_URL, params=params,
                                headers=self._HEADERS, timeout=15)
            resp.raise_for_status()
            result = resp.json().get("Result")
            if not result:
                return None
            return result[0] if isinstance(result, list) else result
        except Exception as e:
            logger.warning(f"Baidu vapi failed for {market_type}-{code}: {e}")
            return None

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

    # ── Tab parsers ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_tab_content(raw: Dict, tab_index: int) -> Optional[Dict]:
        """从 opendata 返回中提取指定 tab 的 content"""
        results = raw.get("Result", [])
        if not isinstance(results, list):
            return None
        # tabs 在 Result[3] (jr_stock_news) 下
        for item in results:
            dd = item.get("DisplayData", {}).get("resultData", {}).get("tplData", {})
            tabs = dd.get("result", {}).get("tabs")
            if tabs and isinstance(tabs, list) and len(tabs) > tab_index:
                return tabs[tab_index].get("content", {})
        return None

    def _parse_quote(self, raw: Dict) -> Optional[Dict]:
        """解析 vapi 行情数据"""
        sf = self._safe_float
        basic = raw.get("basicinfos", {})
        cur = raw.get("cur", {})
        pankou = raw.get("pankouinfos", {})

        if not basic.get("code"):
            return None

        result: Dict[str, Any] = {
            "code": basic.get("code"),
            "name": basic.get("name"),
            "exchange": basic.get("exchange"),
            "status": basic.get("tradeStatusCN", basic.get("stockStatus")),
        }

        result["quote"] = {
            "price": sf(cur.get("price")),
            "change": sf(cur.get("increase")),
            "change_pct": sf(cur.get("ratio")),
            "volume": sf(cur.get("volume")),
            "amount": sf(cur.get("amount")),
            "avg_price": sf(cur.get("avgPrice")),
        }

        indicators = {}
        for item in pankou.get("list", []):
            ename = item.get("ename", "")
            val = item.get("originValue", item.get("value"))
            if ename:
                indicators[ename] = val
        result["indicators"] = indicators

        asks = [{"price": sf(a.get("askprice")), "volume": sf(a.get("askvolume"))}
                for a in raw.get("askinfos", [])]
        bids = [{"price": sf(b.get("bidprice")), "volume": sf(b.get("bidvolume"))}
                for b in raw.get("buyinfos", [])]
        result["order_book"] = {"asks": asks, "bids": bids}

        tags = [t.get("desc") for t in raw.get("tag_list", []) if t.get("desc")]
        if tags:
            result["tags"] = tags

        update = raw.get("update", {})
        if update.get("time"):
            result["update_time"] = update["time"]

        return result

    @staticmethod
    def _parse_capital(content: Dict) -> Dict:
        """解析资金 tab"""
        result: Dict[str, Any] = {}

        # 日资金流向 (最近 N 日)
        day = content.get("fundFlowDay", {}).get("result", {})
        if day:
            main = day.get("main", [])
            retail = day.get("retail", [])
            result["daily"] = {
                "unit": content.get("fundFlowDay", {}).get("unit", "亿元"),
                "main": main[-10:] if len(main) > 10 else main,     # 最近10天
                "retail": retail[-10:] if len(retail) > 10 else retail,
            }

        # 资金分布 (超大/大/中/小单)
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

        # 分钟级资金 (最近 20 条)
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

        # 关键指标
        main_sheet = content.get("mainSheet", {})
        charts = main_sheet.get("chartInfo", [])
        if charts:
            # 取第一组 (季报维度), 每条 = [期间, ROE, ROE同比, ROA, ROA同比, ...]
            c = charts[0]
            headers = c.get("header", [])
            body = c.get("body", [])
            result["key_metrics"] = {
                "headers": ["period"] + headers + [f"{h}_yoy" for h in headers],
                "data": body[-5:] if len(body) > 5 else body,
            }

        # 利润表
        ps = content.get("profitSheet", {})
        ps_chart = ps.get("chartInfo", [])
        if ps_chart:
            result["profit"] = {
                "headers": ["period"] + ps_chart[0].get("header", []),
                "data": ps_chart[0].get("body", []),
            }

        # 资产负债表
        bs = content.get("balanceSheet", {})
        bs_chart = bs.get("chartInfo", [])
        if bs_chart:
            result["balance"] = {
                "headers": ["period"] + bs_chart[0].get("header", []),
                "data": bs_chart[0].get("body", []),
            }

        # 现金流量表
        cf = content.get("cashFlowSheet", {})
        cf_chart = cf.get("chartInfo", [])
        if cf_chart:
            result["cashflow"] = {
                "headers": ["period"] + cf_chart[0].get("header", []),
                "data": cf_chart[0].get("body", []),
            }

        # 主营构成
        comp = content.get("components", {})
        comp_list = comp.get("list", [])
        if comp_list:
            result["components"] = []
            for item in comp_list[:2]:  # 最近两期
                result["components"].append({
                    "period": item.get("title"),
                    "headers": item.get("header", []),
                    "data": item.get("body", []),
                })

        # 估值数据 (最近值)
        vd = content.get("valuationData", {})
        vd_charts = vd.get("chartInfo", [])
        if vd_charts:
            latest_vals = {}
            for vc in vd_charts:
                name = vc.get("header", [""])[0]
                body = vc.get("body", [])
                if body:
                    latest_vals[name] = body[-1]  # [date, value]
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

        # 股东股本
        sh = nc.get("shareholderEquity", {})
        if sh.get("info"):
            result["shareholder"] = {
                item.get("text"): (item["value"].get("sum", item["value"])
                                   if isinstance(item.get("value"), dict) else item.get("value"))
                for item in sh["info"] if item.get("text")
            }

        # 机构评级
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

        # 高管信息
        exec_info = nc.get("executiveInfo", {})
        if exec_info.get("body"):
            result["executives"] = [{
                "name": e.get("executive"),
                "post": e.get("post"),
                "shares": e.get("holdingCapital"),
            } for e in exec_info["body"][:10]]

        # 分红送转
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

    # ── Public methods ─────────────────────────────────────────────────────────

    async def get_stock_quote(self, stock_input: str, tab: str = "quote") -> Dict[str, Any]:
        """
        获取百度股市通股票数据

        Args:
            stock_input: 百度股市通 URL 或股票代码
            tab: 数据类型
                 'quote'    — 实时行情+盘口 (默认)
                 'capital'  — 资金流向 (日/周/月/分钟/分布)
                 'finance'  — 财务数据 (关键指标/三表/主营构成/估值)
                 'company'  — 公司信息 (行业/概念/基本资料)
                 'news'     — 最新资讯
        """
        try:
            market_type, code = self._resolve_input(stock_input)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        loop = asyncio.get_running_loop()

        meta = {
            "source": "baidu_gushitong",
            "tab": tab,
            "url": f"https://gushitong.baidu.com/stock/{market_type}-{code}",
        }

        # 行情 tab — 用 vapi
        if tab == "quote":
            raw = await loop.run_in_executor(None, self._fetch_vapi, market_type, code)
            if not raw:
                return {"success": False, "error": f"百度股市通未返回数据: {market_type}-{code}"}
            parsed = self._parse_quote(raw)
            if not parsed:
                return {"success": False, "error": f"数据解析失败: {market_type}-{code}"}
            return {"success": True, "data": parsed, "metadata": meta}

        # 其他 tab — 用 opendata
        tab_index = _TAB_INDEX.get(tab)
        if tab_index is None:
            return {"success": False, "error": f"未知 tab: {tab}，可选: quote/capital/finance/company/news"}

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
