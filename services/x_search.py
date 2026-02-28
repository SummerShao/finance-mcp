"""
X (Twitter) 搜索服务
工具: search_x_posts
"""
import os
import math
import logging
import requests
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class XSearchService:
    BASE_URL = "https://api.x.com/2/tweets/search/recent"

    def __init__(self):
        self.api_key = os.getenv("X_API_KEY")
        if not self.api_key:
            logger.warning("X_API_KEY not set")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _score(self, metrics: Dict, created_at: str) -> float:
        """按热度+时间衰减打分（6小时半衰期）"""
        base = (
            1.5 * math.log(metrics.get("impression_count", 0) + 1)
            + 1.0 * math.log(metrics.get("like_count", 0) + 1)
            + 2.0 * math.log(metrics.get("retweet_count", 0) + 1)
            + 1.0 * math.log(metrics.get("reply_count", 0) + 1)
        )
        try:
            t = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            hours = (datetime.now(t.tzinfo) - t).total_seconds() / 3600
            decay = math.exp(-hours / 6.0)
        except Exception:
            decay = 1.0
        return round(base * decay, 2)

    def _fetch(self, query: str, max_results: int) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            resp = requests.get(
                self.BASE_URL,
                headers=self.headers,
                params={
                    "query": query,
                    "max_results": min(max_results, 100),
                    "tweet.fields": "created_at,public_metrics,author_id,lang",
                    "expansions": "author_id",
                    "user.fields": "username,name,verified",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"X API HTTP {resp.status_code}: {resp.text[:500]}")
            return None
        except Exception as e:
            logger.error(f"X API fetch failed: {e}")
            return None

    def search_x_posts(
        self,
        query: str,
        max_results: int = 20,
        exclude_retweets: bool = True,
        exclude_replies: bool = True,
        require_links: bool = True,
        language: str = "en",
        min_engagement: int = 5,
    ) -> Dict[str, Any]:
        """搜索 X 帖子并按热度+时间排序，适合市场情绪分析"""
        parts = [f"({query})"]
        if exclude_retweets:
            parts.append("-is:retweet")
        if exclude_replies:
            parts.append("-is:reply")
        if require_links:
            parts.append("has:links")
        if language:
            parts.append(f"lang:{language}")
        full_query = " ".join(parts)

        raw = self._fetch(full_query, max_results=100)
        if raw is None:
            return {
                "success": False,
                "query_used": full_query,
                "error": "Failed to fetch from X API",
            }

        tweets = raw.get("data", [])
        users = {u["id"]: u for u in raw.get("includes", {}).get("users", [])}

        results: List[Dict] = []
        for t in tweets:
            m = t.get("public_metrics", {})
            eng = m.get("like_count", 0) + m.get("retweet_count", 0) + m.get("reply_count", 0)
            if eng < min_engagement:
                continue
            author = users.get(t.get("author_id"), {})
            uname = author.get("username", "unknown")
            results.append({
                "id": t["id"],
                "text": t.get("text"),
                "created_at": t.get("created_at"),
                "author": {
                    "username": uname,
                    "name": author.get("name"),
                    "verified": author.get("verified", False),
                },
                "metrics": {
                    "impressions": m.get("impression_count", 0),
                    "likes": m.get("like_count", 0),
                    "retweets": m.get("retweet_count", 0),
                    "replies": m.get("reply_count", 0),
                    "total_engagement": eng,
                },
                "score": self._score(m, t.get("created_at", "")),
                "url": f"https://x.com/{uname}/status/{t['id']}",
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        final = results[:max_results]

        return {
            "success": True,
            "query_used": full_query,
            "results_count": len(final),
            "results": final,
            "metadata": {
                "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_fetched": len(tweets),
                "after_filtering": len(results),
                "returned": len(final),
            },
        }
