"""
Finnhub 美股数据服务
提供公司基本面、行情、财务、分析师评级、新闻情绪等数据
"""
import os
import datetime
import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import finnhub
    FINNHUB_AVAILABLE = True
except ImportError:
    FINNHUB_AVAILABLE = False
    logger.warning("finnhub-python not installed")


class FinnhubService:
    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY")
        self.client = None
        if FINNHUB_AVAILABLE and self.api_key:
            try:
                self.client = finnhub.Client(api_key=self.api_key)
                logger.info("FinnhubService initialized")
            except Exception as e:
                logger.error(f"Finnhub init failed: {e}")

    def _call(self, func, *args, **kwargs) -> Any:
        if not self.client:
            return None
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Finnhub API call failed: {e}")
            return None

    def _ts(self, date_str: str, end_of_day: bool = False) -> int:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())

    def _ok(self, data: Any, **meta) -> Dict:
        return {"success": True, "data": data, "metadata": meta}

    def _err(self, msg: str, **meta) -> Dict:
        return {"success": False, "error": msg, "metadata": meta}

    # ── Company profile ──────────────────────────────────────────────────────

    async def get_company_profile(self, symbol: str) -> Dict:
        return self._ok({
            "profile": self._call(self.client.company_profile2, symbol=symbol),
            "peers": self._call(self.client.company_peers, symbol),
        }, symbol=symbol) if self.client else self._err("Finnhub not initialized")

    # ── Market data ──────────────────────────────────────────────────────────

    async def get_quote(self, symbol: str) -> Dict:
        data = self._call(self.client.quote, symbol) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    # ── Financials ───────────────────────────────────────────────────────────

    async def get_financials(self, symbol: str, start_date: str, end_date: str) -> Dict:
        return self._ok({
            "basic_financials": self._call(self.client.company_basic_financials, symbol, "all"),
            "earnings_surprises": self._call(self.client.company_earnings, symbol, limit=4),
            "dividends": self._call(self.client.stock_dividends, symbol, _from=start_date, to=end_date),
        }, symbol=symbol, period=f"{start_date}/{end_date}") if self.client else self._err("Not initialized")

    # ── Ownership & transactions ─────────────────────────────────────────────

    async def get_ownership(self, symbol: str, start_date: str, end_date: str) -> Dict:
        return self._ok({
            "institutional": self._call(self.client.ownership, symbol, limit=10),
            "fund": self._call(self.client.fund_ownership, symbol, limit=10),
            "insider_transactions": self._call(self.client.stock_insider_transactions, symbol, start_date, end_date),
        }, symbol=symbol) if self.client else self._err("Not initialized")

    # ── Executive & filings ──────────────────────────────────────────────────

    async def get_executives(self, symbol: str) -> Dict:
        data = self._call(self.client.company_executive, symbol) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    async def get_sec_filings(self, symbol: str, start_date: str, end_date: str) -> Dict:
        data = self._call(self.client.filings, symbol=symbol, _from=start_date, to=end_date) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    # ── Earnings call transcripts ────────────────────────────────────────────

    async def get_transcripts(self, symbol: str) -> Dict:
        if not self.client:
            return self._err("Not initialized")
        lst = self._call(self.client.transcripts_list, symbol)
        result: Dict[str, Any] = {"list": lst}
        if isinstance(lst, list) and lst:
            latest_id = lst[0].get("id") if isinstance(lst[0], dict) else None
            if latest_id:
                result["latest_content"] = self._call(self.client.transcripts, latest_id)
        return self._ok(result, symbol=symbol)

    # ── Sentiment & news ─────────────────────────────────────────────────────

    async def get_news_sentiment(self, symbol: str) -> Dict:
        data = self._call(self.client.news_sentiment, symbol) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    async def get_social_sentiment(self, symbol: str) -> Dict:
        data = self._call(self.client.stock_social_sentiment, symbol) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    async def get_insider_sentiment(self, symbol: str, start_date: str, end_date: str) -> Dict:
        data = self._call(self.client.stock_insider_sentiment, symbol, start_date, end_date) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    async def get_upgrade_downgrade(self, symbol: str, start_date: str, end_date: str) -> Dict:
        data = self._call(self.client.upgrade_downgrade, symbol=symbol, _from=start_date, to=end_date) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    async def get_news(self, symbol: str, start_date: str, end_date: str) -> Dict:
        news = self._call(self.client.company_news, symbol, _from=start_date, to=end_date) if self.client else None
        if isinstance(news, list):
            news = news[:10]
        return self._ok(news, symbol=symbol) if news else self._err("No data", symbol=symbol)

    async def get_recommendation_trends(self, symbol: str) -> Dict:
        data = self._call(self.client.recommendation_trends, symbol) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    # ── Technical signals ────────────────────────────────────────────────────

    async def get_patterns(self, symbol: str, resolution: str = "D") -> Dict:
        data = self._call(self.client.pattern_recognition, symbol, resolution) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    async def get_support_resistance(self, symbol: str, resolution: str = "D") -> Dict:
        data = self._call(self.client.support_resistance, symbol, resolution) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    async def get_aggregate_indicator(self, symbol: str, resolution: str = "D") -> Dict:
        data = self._call(self.client.aggregate_indicator, symbol, resolution) if self.client else None
        return self._ok(data, symbol=symbol) if data else self._err("No data", symbol=symbol)

    # ── Historical candles ───────────────────────────────────────────────────

    async def get_candles(self, symbol: str, start_date: str, end_date: str, resolution: str = "D") -> Dict:
        if not self.client:
            return self._err("Finnhub not initialized")
        _from = self._ts(start_date)
        to = self._ts(end_date, end_of_day=True)
        data = self._call(self.client.stock_candles, symbol, resolution, _from, to)
        return self._ok(data, symbol=symbol, resolution=resolution) if data else self._err("No data", symbol=symbol)
