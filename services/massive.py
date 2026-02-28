"""
Polygon.io (Massive) 技术指标服务
提供 SMA / EMA / MACD / RSI 等技术指标
"""
import os
import datetime
import logging
import requests
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MassiveService:
    def __init__(self):
        self.api_key = os.getenv("POLYGON_API_KEY")
        self.base_url = os.getenv("MASSIVE_API_URL", "https://api.polygon.io")
        if not self.api_key:
            logger.warning("POLYGON_API_KEY not set")

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Any]:
        if not self.api_key:
            return None
        p = {**(params or {}), "apiKey": self.api_key}
        try:
            resp = requests.get(f"{self.base_url}{endpoint}", params=p, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Polygon API call failed ({endpoint}): {e}")
            return None

    def _indicator(self, path: str, ticker: str, params: Dict) -> Optional[list]:
        resp = self._get(f"/v1/indicators/{path}/{ticker.upper()}", params)
        if resp and "results" in resp:
            return resp["results"].get("values")
        return None

    # ── Moving averages ──────────────────────────────────────────────────────

    async def get_sma(self, ticker: str, window: int = 20, limit: int = 10) -> Optional[list]:
        return self._indicator("sma", ticker, {
            "timespan": "day", "window": window,
            "series_type": "close", "adjusted": "true",
            "limit": limit, "order": "desc",
        })

    async def get_ema(self, ticker: str, window: int = 20, limit: int = 10) -> Optional[list]:
        return self._indicator("ema", ticker, {
            "timespan": "day", "window": window,
            "series_type": "close", "adjusted": "true",
            "limit": limit, "order": "desc",
        })

    # ── Momentum ─────────────────────────────────────────────────────────────

    async def get_macd(self, ticker: str, limit: int = 10) -> Optional[list]:
        return self._indicator("macd", ticker, {
            "timespan": "day", "short_window": 12,
            "long_window": 26, "signal_window": 9,
            "series_type": "close", "adjusted": "true",
            "limit": limit, "order": "desc",
        })

    async def get_rsi(self, ticker: str, window: int = 14, limit: int = 10) -> Optional[list]:
        return self._indicator("rsi", ticker, {
            "timespan": "day", "window": window,
            "series_type": "close", "adjusted": "true",
            "limit": limit, "order": "desc",
        })
