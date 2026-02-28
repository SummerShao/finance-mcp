"""
美股综合分析服务
工具: get_fundamental_analysis, get_technical_analysis,
      get_sentiment_analysis, get_comprehensive_analysis
"""
import logging
from datetime import datetime
from typing import Any, Dict

from .finnhub import FinnhubService
from .massive import MassiveService

logger = logging.getLogger(__name__)


class USStockService:
    def __init__(self):
        self.finnhub = FinnhubService()
        self.massive = MassiveService()

    def _meta(self, symbol: str, start_date: str, end_date: str, analysis_type: str) -> Dict:
        return {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "analysis_type": analysis_type,
            "timestamp": datetime.now().isoformat(),
        }

    # ── Fundamental ──────────────────────────────────────────────────────────

    async def get_fundamental_analysis(self, symbol: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        美股基本面分析：公司概况、财务指标、股权结构、高管信息、SEC 文件、财报电话会议

        Args:
            symbol: 股票代码，如 'AAPL', 'TSLA'
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        """
        data: Dict[str, Any] = {}
        try:
            profile = await self.finnhub.get_company_profile(symbol)
            if profile.get("success"):
                data["company_profile"] = profile["data"]

            financials = await self.finnhub.get_financials(symbol, start_date, end_date)
            if financials.get("success"):
                data["financial_metrics"] = financials["data"]

            ownership = await self.finnhub.get_ownership(symbol, start_date, end_date)
            if ownership.get("success"):
                data["ownership"] = ownership["data"]

            execs = await self.finnhub.get_executives(symbol)
            if execs.get("success"):
                data["executives"] = execs["data"]

            filings = await self.finnhub.get_sec_filings(symbol, start_date, end_date)
            if filings.get("success"):
                data["sec_filings"] = filings["data"]

            transcripts = await self.finnhub.get_transcripts(symbol)
            if transcripts.get("success"):
                data["earnings_calls"] = transcripts["data"]

            return {"success": True, "data": data, "metadata": self._meta(symbol, start_date, end_date, "fundamental")}

        except Exception as e:
            logger.error(f"Fundamental analysis failed for {symbol}: {e}")
            return {"success": False, "error": str(e), "metadata": self._meta(symbol, start_date, end_date, "fundamental")}

    # ── Technical ────────────────────────────────────────────────────────────

    async def get_technical_analysis(self, symbol: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        美股技术分析：均线(SMA/EMA)、动量指标(RSI/MACD)、形态识别、支撑阻力、综合信号

        Args:
            symbol: 股票代码，如 'AAPL', 'TSLA'
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        """
        data: Dict[str, Any] = {}
        try:
            quote = await self.finnhub.get_quote(symbol)
            if quote.get("success"):
                data["quote"] = quote["data"]

            data["moving_averages"] = {
                "sma_20": await self.massive.get_sma(symbol, window=20),
                "sma_50": await self.massive.get_sma(symbol, window=50),
                "sma_200": await self.massive.get_sma(symbol, window=200),
                "ema_12": await self.massive.get_ema(symbol, window=12),
                "ema_26": await self.massive.get_ema(symbol, window=26),
            }

            data["momentum"] = {
                "rsi": await self.massive.get_rsi(symbol),
                "macd": await self.massive.get_macd(symbol),
            }

            patterns = await self.finnhub.get_patterns(symbol)
            if patterns.get("success"):
                data["patterns"] = patterns["data"]

            sr = await self.finnhub.get_support_resistance(symbol)
            if sr.get("success"):
                data["support_resistance"] = sr["data"]

            agg = await self.finnhub.get_aggregate_indicator(symbol)
            if agg.get("success"):
                data["aggregate_signals"] = agg["data"]

            return {"success": True, "data": data, "metadata": self._meta(symbol, start_date, end_date, "technical")}

        except Exception as e:
            logger.error(f"Technical analysis failed for {symbol}: {e}")
            return {"success": False, "error": str(e), "metadata": self._meta(symbol, start_date, end_date, "technical")}

    # ── Sentiment ────────────────────────────────────────────────────────────

    async def get_sentiment_analysis(self, symbol: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        美股情绪分析：新闻情绪、社交媒体情绪、内部人情绪、分析师评级变化

        Args:
            symbol: 股票代码，如 'AAPL', 'TSLA'
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        """
        data: Dict[str, Any] = {}
        try:
            news_sentiment = await self.finnhub.get_news_sentiment(symbol)
            if news_sentiment.get("success"):
                data["news_sentiment"] = news_sentiment["data"]

            social = await self.finnhub.get_social_sentiment(symbol)
            if social.get("success"):
                data["social_sentiment"] = social["data"]

            insider = await self.finnhub.get_insider_sentiment(symbol, start_date, end_date)
            if insider.get("success"):
                data["insider_sentiment"] = insider["data"]

            upgrades = await self.finnhub.get_upgrade_downgrade(symbol, start_date, end_date)
            if upgrades.get("success"):
                data["upgrade_downgrade"] = upgrades["data"]

            recommendations = await self.finnhub.get_recommendation_trends(symbol)
            if recommendations.get("success"):
                data["recommendation_trends"] = recommendations["data"]

            news = await self.finnhub.get_news(symbol, start_date, end_date)
            if news.get("success"):
                data["recent_news"] = news["data"]

            return {"success": True, "data": data, "metadata": self._meta(symbol, start_date, end_date, "sentiment")}

        except Exception as e:
            logger.error(f"Sentiment analysis failed for {symbol}: {e}")
            return {"success": False, "error": str(e), "metadata": self._meta(symbol, start_date, end_date, "sentiment")}

    # ── Historical K-line ────────────────────────────────────────────────────

    async def get_stock_history(self, symbol: str, start_date: str, end_date: str, resolution: str = "D") -> Dict[str, Any]:
        """
        美股历史 K 线（OHLCV）

        Args:
            symbol: 股票代码，如 'AAPL', 'TSLA'
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            resolution: K 线周期，'D'=日(默认),'W'=周,'M'=月,'1'/'5'/'15'/'30'/'60'=分钟
        """
        try:
            candles = await self.finnhub.get_candles(symbol, start_date, end_date, resolution)
            return {"success": True, "data": candles.get("data"), "metadata": self._meta(symbol, start_date, end_date, "history")}
        except Exception as e:
            logger.error(f"Stock history failed for {symbol}: {e}")
            return {"success": False, "error": str(e), "metadata": self._meta(symbol, start_date, end_date, "history")}

    # ── Comprehensive ────────────────────────────────────────────────────────

    async def get_comprehensive_analysis(self, symbol: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        美股全维度综合分析：基本面 + 技术面 + 情绪面一次性返回

        Args:
            symbol: 股票代码，如 'AAPL', 'TSLA'
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        """
        try:
            fundamental, technical, sentiment = await _gather(
                self.get_fundamental_analysis(symbol, start_date, end_date),
                self.get_technical_analysis(symbol, start_date, end_date),
                self.get_sentiment_analysis(symbol, start_date, end_date),
            )
            return {
                "success": True,
                "data": {
                    "fundamental": fundamental.get("data"),
                    "technical": technical.get("data"),
                    "sentiment": sentiment.get("data"),
                },
                "metadata": self._meta(symbol, start_date, end_date, "comprehensive"),
            }
        except Exception as e:
            logger.error(f"Comprehensive analysis failed for {symbol}: {e}")
            return {"success": False, "error": str(e), "metadata": self._meta(symbol, start_date, end_date, "comprehensive")}


import asyncio

async def _gather(*coros):
    return await asyncio.gather(*coros)
