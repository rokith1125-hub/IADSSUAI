"""
News aggregator for ULAGA_UNAVU
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

try:
    from services.news_service import NewsService
except ImportError:
    from services.news_service import NewsService

logger = logging.getLogger(__name__)


class NewsAggregator:
    """Agriculture news aggregator with strict DTO formatting."""

    PRIORITY_CATEGORIES = {"market", "weather", "pest", "government", "policy", "crop"}

    def __init__(self):
        self.news_service = NewsService()
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        self.tavily_client = self._init_tavily()

    def _init_tavily(self):
        """Initialize Tavily client."""
        try:
            if self.tavily_api_key:
                from tavily import TavilyClient

                return TavilyClient(api_key=self.tavily_api_key)
        except ImportError:
            logger.warning("Tavily package not installed")
        except Exception as e:
            logger.error(f"Tavily init error: {str(e)}")
        return None

    def search_agriculture_news(self, query: str = None, limit: int = 10) -> List[Dict]:
        """Search for agriculture news using Tavily API."""
        try:
            if not self.tavily_client:
                return self.get_agriculture_news(limit=limit)

            search_query = query or "agriculture India farming crops weather market prices government scheme Tamil Nadu"
            response = self.tavily_client.search(
                query=search_query,
                search_depth="basic",
                max_results=limit,
                include_raw_content=False,
            )

            raw_items: List[Dict] = []
            for result in response.get("results", []):
                content = result.get("content", "") or ""
                score = self._safe_float(result.get("score"), default=0.0)
                raw_items.append(
                    {
                        "title": result.get("title", ""),
                        "summary": content[:260].strip(),
                        "url": result.get("url", ""),
                        "source": result.get("source", "Unknown"),
                        "category": self._categorize_news(content),
                        "published_at": result.get("published_date") or datetime.now(timezone.utc).isoformat(),
                        "image_url": result.get("image") or result.get("image_url") or "",
                        "importance": "high" if score > 0.8 else "normal",
                        "is_important": score > 0.8,
                        "relevance_score": score,
                    }
                )

            return self._format_news_list(raw_items)[:limit]
        except Exception as e:
            logger.error(f"Tavily search error: {str(e)}")
            return self.get_agriculture_news(limit=limit)

    def _categorize_news(self, content: str) -> str:
        """Categorize news based on content."""
        content_lower = (content or "").lower()

        categories = {
            "market": ["price", "mandi", "market", "export", "import", "trade", "msp"],
            "weather": ["weather", "rain", "monsoon", "drought", "flood", "climate"],
            "pest": ["disease", "pest", "insect", "crop failure", "blight"],
            "government": ["scheme", "subsidy", "pm-kisan", "government", "ministry"],
            "policy": ["policy", "regulation", "bill", "act", "notification"],
            "crop": ["crop", "seed", "harvest", "yield", "cultivation", "farming"],
        }

        for category, keywords in categories.items():
            if any(kw in content_lower for kw in keywords):
                return category

        return "crop"

    def get_todays_news_with_lang(self, lang: str = "en", limit: int = 10, refresh: bool = False) -> List[Dict]:
        """Get today's agriculture news with language support."""
        raw_items = self.news_service.get_todays_agricultural_news(lang=lang, limit=max(limit * 2, 20), refresh=refresh)
        return self._format_news_list(raw_items)[:limit]

    def get_agriculture_news(self, limit: int = 10, refresh: bool = False) -> List[Dict]:
        """Get agriculture news with optional cache bypass."""
        raw_items = self.news_service.get_agriculture_news(limit=max(limit * 2, 20), refresh=refresh)
        return self._format_news_list(raw_items)[:limit]

    def get_news_for_farmers(self, location: str = None, crop: str = None, lang: str = "en") -> List[Dict]:
        """Get personalized news for farmers with language support."""
        items = self.get_todays_news_with_lang(lang=lang, limit=25)
        location_q = (location or "").strip().lower()
        crop_q = (crop or "").strip().lower()

        if not location_q and not crop_q:
            return items[:10]

        filtered: List[Dict] = []
        for item in items:
            hay = f"{item.get('title', '')} {item.get('summary', '')}".lower()
            location_ok = (not location_q) or (location_q in hay)
            crop_ok = (not crop_q) or (crop_q in hay)
            if location_ok and crop_ok:
                filtered.append(item)

        return filtered[:10] if filtered else items[:10]

    def get_news_summary(self) -> Dict:
        """Get summary of today's agriculture news."""
        return self.news_service.get_news_summary()

    def get_news_by_category(self, category: str, limit: int = 5) -> List[Dict]:
        """Get news by category."""
        try:
            all_news = self.get_agriculture_news(limit=40)
            if category.lower() == "all":
                return all_news[:limit]

            filtered = [item for item in all_news if item.get("category", "").lower() == category.lower()]
            return filtered[:limit]
        except Exception as e:
            logger.error(f"News by category error: {str(e)}")
            return []

    def search_news(self, query: str, limit: int = 10) -> List[Dict]:
        """Search news by query."""
        try:
            all_news = self.get_agriculture_news(limit=80)
            q = (query or "").lower().strip()
            if not q:
                return []

            results = []
            for item in all_news:
                title = item.get("title", "").lower()
                summary = item.get("summary", "").lower()
                if q in title or q in summary:
                    results.append(item)
                if len(results) >= limit:
                    break

            return results
        except Exception as e:
            logger.error(f"Search news error: {str(e)}")
            return []

    def get_trending_topics(self) -> List[Dict]:
        """Get trending agriculture topics."""
        try:
            all_news = self.get_agriculture_news(limit=40)
            category_count: Dict[str, int] = {}
            for item in all_news:
                category = item.get("category", "general")
                category_count[category] = category_count.get(category, 0) + 1

            trending = [
                {
                    "category": category,
                    "count": count,
                    "icon": self._get_category_icon(category),
                }
                for category, count in category_count.items()
            ]
            trending.sort(key=lambda x: x["count"], reverse=True)
            return trending[:5]
        except Exception as e:
            logger.error(f"Trending topics error: {str(e)}")
            return []

    def get_trending_news(self, limit: int = 5, lang: str = "en") -> List[Dict]:
        """Get trending agriculture news with weighted score."""
        try:
            all_news = self.get_todays_news_with_lang(lang=lang, limit=max(limit * 4, 25))
            for item in all_news:
                item["trending_score"] = self._calculate_trending_score(item)

            all_news.sort(key=lambda x: x.get("trending_score", 0), reverse=True)
            return all_news[:limit]
        except Exception as e:
            logger.error(f"Trending news error: {str(e)}")
            return []

    def clear_cache(self):
        """Clear underlying news cache."""
        self.news_service.clear_cache()

    def get_latest_updates(self, hours: int = 24) -> List[Dict]:
        """Get latest updates from last N hours."""
        try:
            all_news = self.get_agriculture_news(limit=40)
            cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
            latest: List[Dict] = []
            for item in all_news:
                published_at = item.get("published_at")
                published_ts = self._to_timestamp(published_at)
                if published_ts >= cutoff:
                    latest.append(item)
            return latest if latest else all_news[:10]
        except Exception as e:
            logger.error(f"Latest updates error: {str(e)}")
            return []

    def _get_category_icon(self, category: str) -> str:
        """Get icon for category."""
        icons = {
            "market": "money",
            "weather": "weather",
            "disease": "alert",
            "government": "gov",
            "technology": "tech",
            "organic": "leaf",
            "general": "news",
        }
        return icons.get(category.lower(), "news")

    def _format_news_list(self, items: List[Dict]) -> List[Dict]:
        formatted = [self._format_news_item(item) for item in items or []]
        deduped = self._deduplicate_by_title(formatted)
        deduped.sort(key=lambda x: self._to_timestamp(x.get("published_at")), reverse=True)
        return deduped

    def _format_news_item(self, raw: Dict) -> Dict:
        title = (raw.get("title") or "").strip()
        summary = (raw.get("summary") or raw.get("description") or raw.get("content") or "").strip()
        category = (raw.get("category") or self._categorize_news(f"{title} {summary}"))
        category = str(category).lower().strip() or "general"

        published_at = raw.get("published_at") or raw.get("date") or datetime.now(timezone.utc).isoformat()
        published_at = self._normalize_iso_datetime(published_at)

        relevance = self._safe_float(raw.get("relevance_score"), default=None)
        if relevance is None:
            importance = str(raw.get("importance", "normal")).lower()
            relevance = 0.85 if importance == "high" else 0.65 if importance == "medium" else 0.45
        relevance = max(0.0, min(1.0, relevance))

        url = (raw.get("url") or "").strip()
        if not self._is_valid_url(url):
            url = ""

        image_url = (raw.get("image_url") or raw.get("image") or raw.get("thumbnail") or "").strip()
        if not self._is_valid_url(image_url):
            image_url = self._fallback_image(category)

        slug_base = title or url or f"{category}-{published_at}"
        slug = self._slugify(slug_base)
        item_id = raw.get("id") or url or slug

        is_important = bool(raw.get("is_important")) or relevance > 0.8

        return {
            "id": str(item_id),
            "title": title,
            "summary": summary,
            "image_url": image_url,
            "url": url,
            "source": raw.get("source") or "Unknown",
            "category": category,
            "published_at": published_at,
            "date": published_at,
            "is_important": is_important,
            "importance": "high" if is_important else "normal",
            "relevance_score": round(relevance, 4),
            "slug": slug,
        }

    def _calculate_trending_score(self, item: Dict) -> float:
        relevance_part = (self._safe_float(item.get("relevance_score"), default=0.0) or 0.0) * 50.0
        category_part = 20.0 if item.get("category") in self.PRIORITY_CATEGORIES else 10.0
        recency_part = self._recency_weight(item.get("published_at"))
        return round(relevance_part + category_part + recency_part, 4)

    def _recency_weight(self, published_at: str) -> float:
        ts = self._to_timestamp(published_at)
        age_hours = max(0.0, (datetime.now(timezone.utc).timestamp() - ts) / 3600.0)
        if age_hours <= 6:
            return 20.0
        if age_hours <= 24:
            return 16.0
        if age_hours <= 72:
            return 12.0
        if age_hours <= 168:
            return 8.0
        return 4.0

    def _to_timestamp(self, value: Optional[str]) -> float:
        if not value:
            return 0.0
        text = str(value).strip()
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
        ]
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                continue
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return 0.0

    def _normalize_iso_datetime(self, value: Optional[str]) -> str:
        ts = self._to_timestamp(value)
        if ts <= 0:
            return datetime.now(timezone.utc).isoformat()
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    def _deduplicate_by_title(self, items: List[Dict]) -> List[Dict]:
        seen = set()
        out = []
        for item in items:
            title = (item.get("title") or "").lower().strip()
            key = " ".join(title.split())
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _is_valid_url(self, value: str) -> bool:
        if not value:
            return False
        try:
            parsed = urlparse(value)
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except Exception:
            return False

    def _fallback_image(self, category: str) -> str:
        return ""

    def _slugify(self, value: str) -> str:
        text = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or ""))
        while "--" in text:
            text = text.replace("--", "-")
        return text.strip("-") or "news-item"

    def _safe_float(self, value, default: Optional[float] = 0.0) -> Optional[float]:
        try:
            return float(value)
        except Exception:
            return default
