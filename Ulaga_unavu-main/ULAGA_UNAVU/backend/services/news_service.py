"""
News service for agriculture news aggregation
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os
import re
import importlib.util
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from services.local_storage import db_service
from utils.error_handler import APIError

logger = logging.getLogger(__name__)

class NewsService:
    """Service for agriculture news aggregation"""
    
    def __init__(self):
        self.cache = {}
        self.cache_timeout = 3600  # 1 hour for news
        self.image_cache = {}
        self.image_cache_timeout = 21600  # 6 hours for image URLs
        self.feedparser_available = importlib.util.find_spec("feedparser") is not None
        self.enable_remote_image_fetch = os.getenv("ENABLE_NEWS_REMOTE_IMAGE_FETCH", "false").lower() == "true"
        self.tavily_timeout_seconds = max(3, int(os.getenv("TAVILY_NEWS_TIMEOUT_SECONDS", "8") or 8))
        self.sources = [
            "https://www.thehindu.com/news/national/",
            "https://indianexpress.com/section/india/",
            "https://www.livemint.com/news/",
            "https://www.business-standard.com/india-news"
        ]
        
        # Agriculture-focused RSS feeds (stable Google News RSS queries).
        self.rss_feeds = [
            "https://news.google.com/rss/search?q=agriculture+India&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=farming+India+market+prices&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=monsoon+crop+India&hl=en-IN&gl=IN&ceid=IN:en",
        ]
        self.allowed_categories = {"crop", "market", "weather", "government", "pest", "policy"}
        self.blocked_keywords = {"politics", "film", "crime", "sports"}
    
    def get_agriculture_news(self, limit: int = 10, refresh: bool = False) -> List[Dict]:
        """Get agriculture news from real sources with persistent cache."""
        cache_key = f"agriculture_news_v1_limit_{int(limit)}"
        now = datetime.utcnow()

        if not refresh:
            cached = db_service.find_one(
                "news_cache",
                {"cache_key": cache_key, "cache_type": "agriculture_news"},
                sort=[("created_at", -1)]
            )
            if cached:
                expires_at = self._parse_iso_datetime(cached.get("expires_at"))
                cached_items = cached.get("news") or []
                if expires_at and expires_at > now and isinstance(cached_items, list):
                    logger.info("Using cached news data")
                    return cached_items[:limit]

        try:
            # Priority 1: Tavily search API.
            news_items = self._get_tavily_news(max(limit * 3, 20))
            # Priority 2: RSS feeds (real source) if Tavily unavailable.
            if not news_items:
                logger.warning("Tavily unavailable for news. Falling back to RSS feeds.")
                news_items = self._get_rss_news(max(limit * 3, 20))
            if not news_items:
                logger.warning("feedparser RSS unavailable. Falling back to direct RSS parsing.")
                news_items = self._get_rss_news_direct(max(limit * 3, 20))

            if not news_items:
                raise APIError("News service unavailable", 503)

            news_items = self._filter_allowed_news(news_items)
            if not news_items:
                raise APIError("News service unavailable", 503)

            news_items = self._deduplicate_news(news_items)
            news_items.sort(key=lambda x: x.get('date', ''), reverse=True)
            news_items = [self._attach_display_fields(item) for item in news_items[:limit]]

            db_service.insert_one(
                "news_cache",
                {
                    "cache_key": cache_key,
                    "cache_type": "agriculture_news",
                    "news": news_items,
                    "expires_at": (now + timedelta(seconds=self.cache_timeout)).isoformat(),
                    "source": "tavily_api"
                }
            )
            return news_items
        except APIError:
            raise
        except Exception as e:
            logger.error(f"Error getting agriculture news: {str(e)}")
            raise APIError("News service unavailable", 503)

    def _get_rss_news_direct(self, limit: int) -> List[Dict]:
        """Get RSS news without feedparser dependency using direct XML parsing."""
        try:
            news_items = []
            headers = {
                "User-Agent": "Mozilla/5.0 (ULAGA_UNAVU News Service)"
            }

            for feed_url in self.rss_feeds:
                if len(news_items) >= limit:
                    break
                try:
                    response = requests.get(feed_url, timeout=10, headers=headers)
                    if response.status_code != 200:
                        continue

                    soup = BeautifulSoup(response.content, "xml")
                    channel_title = ""
                    channel = soup.find("channel")
                    if channel:
                        channel_title = (channel.find("title").get_text(strip=True) if channel.find("title") else "")

                    entries = soup.find_all("item")
                    if not entries:
                        entries = soup.find_all("entry")

                    for entry in entries:
                        if len(news_items) >= limit:
                            break

                        title_tag = entry.find("title")
                        desc_tag = entry.find("description") or entry.find("summary") or entry.find("content")
                        link_tag = entry.find("link")
                        pub_tag = entry.find("pubDate") or entry.find("published") or entry.find("updated")

                        title = title_tag.get_text(strip=True) if title_tag else ""
                        summary = desc_tag.get_text(strip=True) if desc_tag else ""
                        if not title:
                            continue
                        if not self._is_agriculture_related(f"{title} {summary}"):
                            continue

                        link = ""
                        if link_tag:
                            href = link_tag.get("href")
                            link = href or link_tag.get_text(strip=True)

                        news_items.append({
                            "title": title,
                            "summary": (summary[:200] + "...") if len(summary) > 200 else summary,
                            "source": channel_title or urlparse(feed_url).netloc,
                            "url": link,
                            "date": pub_tag.get_text(strip=True) if pub_tag else "",
                            "category": self._categorize_news(f"{title} {summary}"),
                            "importance": self._calculate_importance(title),
                        })
                except Exception as feed_error:
                    logger.warning(f"Direct RSS parsing failed for {feed_url}: {str(feed_error)}")
                    continue

            return news_items
        except Exception as e:
            logger.error(f"Direct RSS news error: {str(e)}")
            return []
    
    def _get_tavily_news(self, limit: int) -> List[Dict]:
        """Get news using Tavily API"""
        try:
            api_key = os.getenv('TAVILY_API_KEY')
            if not api_key:
                logger.warning("Tavily API key not configured")
                return []
            
            from tavily import TavilyClient
            
            client = TavilyClient(api_key=api_key)

            # Search for agriculture news with hard timeout to avoid long blocking.
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    client.search,
                    query="agriculture India farming crops weather mandi prices government scheme",
                    search_depth="basic",
                    max_results=limit,
                    include_raw_content=True,
                )
                try:
                    response = future.result(timeout=self.tavily_timeout_seconds)
                except FuturesTimeoutError:
                    future.cancel()
                    logger.warning("Tavily news search timed out after %ss", self.tavily_timeout_seconds)
                    return []
            
            news_items = []
            for result in response.get('results', []):
                # Filter for agriculture-related content
                if self._is_agriculture_related(result.get('content', '')):
                    news_items.append({
                        "title": result.get('title', ''),
                        "summary": result.get('content', '')[:200] + "...",
                        "source": result.get('source', ''),
                        "url": result.get('url', ''),
                        "date": result.get('published_date') or '',
                        "category": self._categorize_news(result.get('content', '')),
                        "importance": self._calculate_importance(result.get('title', ''))
                    })
            
            return news_items
            
        except Exception as e:
            logger.error(f"Tavily API error: {str(e)}")
            return []

    def _get_tamil_news(self, limit: int) -> List[Dict]:
        """Get agriculture news in Tamil using Tavily or specific sources"""
        try:
            api_key = os.getenv('TAVILY_API_KEY')
            if not api_key:
                return []
                
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            
            # Search query in Tamil
            response = client.search(
                query="விவசாய செய்திகள் தமிழ்நாடு சந்தை விலை வானிலை",
                search_depth="advanced",
                max_results=limit
            )
            
            news_items = []
            for result in response.get('results', []):
                news_items.append({
                    "title": result.get('title', ''),
                    "summary": result.get('content', '')[:200] + "...",
                    "source": result.get('source', 'Tamil News'),
                    "url": result.get('url', ''),
                    "date": result.get('published_date') or '',
                    "category": self._categorize_news(result.get('content', '')),
                    "importance": self._calculate_importance(result.get('title', ''))
                })
            return news_items
        except Exception as e:
            logger.error(f"Tamil news error: {str(e)}")
            return []
    
    def _get_rss_news(self, limit: int) -> List[Dict]:
        """Get news from RSS feeds"""
        try:
            if not self.feedparser_available:
                return []

            import feedparser
            
            news_items = []
            
            for feed_url in self.rss_feeds[:2]:  # Limit to 2 feeds
                if len(news_items) >= limit:
                    break
                
                try:
                    feed = feedparser.parse(feed_url)
                    
                    for entry in feed.entries:
                        if len(news_items) >= limit:
                            break
                        
                        # Check if agriculture related
                        title = entry.get('title', '')
                        summary = entry.get('summary', '') or entry.get('description', '')
                        
                        if self._is_agriculture_related(title + " " + summary):
                            news_items.append({
                                "title": title,
                                "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                                "source": feed.feed.get('title', 'RSS Feed'),
                                "url": entry.get('link', ''),
                                "date": entry.get('published', ''),
                                "category": self._categorize_news(title + " " + summary),
                                "importance": self._calculate_importance(title)
                            })
                
                except Exception as feed_error:
                    logger.error(f"RSS feed error {feed_url}: {str(feed_error)}")
                    continue
            
            return news_items
            
        except Exception as e:
            logger.error(f"RSS news error: {str(e)}")
            return []
    
    def _scrape_news(self, limit: int) -> List[Dict]:
        """Scrape news from agriculture websites"""
        try:
            news_items = []
            
            # Scrape from known agriculture news sites
            scrape_targets = [
                ("https://krishijagran.com/latest-news/", "Krishijagran"),
                ("https://www.agriwatch.com/news", "Agriwatch"),
                ("https://www.farmingindia.in/", "Farming India")
            ]
            
            for url, source in scrape_targets:
                if len(news_items) >= limit:
                    break
                
                try:
                    response = requests.get(url, timeout=10, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Look for news articles (this is site-specific)
                        articles = soup.find_all('article') or soup.find_all('div', class_='news-item')
                        
                        for article in articles[:5]:  # Limit per site
                            if len(news_items) >= limit:
                                break
                            
                            title_elem = article.find('h2') or article.find('h3') or article.find('a')
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                summary = article.find('p')
                                summary_text = summary.get_text(strip=True)[:150] + "..." if summary else ""
                                
                                if title and self._is_agriculture_related(title):
                                    # Keep source date truthful: extract if present; otherwise keep empty.
                                    date_text = ""
                                    date_candidate = (
                                        article.find("time")
                                        or article.find(class_=re.compile("date|time", re.I))
                                        or article.find(attrs={"datetime": True})
                                    )
                                    if date_candidate:
                                        date_text = (
                                            date_candidate.get("datetime")
                                            or date_candidate.get_text(strip=True)
                                            or ""
                                        )
                                    news_items.append({
                                        "title": title,
                                        "summary": summary_text,
                                        "source": source,
                                        "url": url,
                                        "date": date_text,
                                        "category": self._categorize_news(title),
                                        "importance": self._calculate_importance(title)
                                    })
                
                except Exception as scrape_error:
                    logger.error(f"Scraping error {url}: {str(scrape_error)}")
                    continue
            
            return news_items
            
        except Exception as e:
            logger.error(f"Web scraping error: {str(e)}")
            return []
            
    def get_todays_agricultural_news(self, lang: str = 'en', limit: int = 10, refresh: bool = False) -> List[Dict]:
        """Fetch today's agriculture news with language preference"""
        return self.get_agriculture_news(limit, refresh=refresh)
    
    def _is_agriculture_related(self, text: str) -> bool:
        """Check if text is agriculture related"""
        text_lower = text.lower()
        
        agriculture_keywords = [
            'agriculture', 'farmer', 'farming', 'crop', 'soil', 'fertilizer',
            'irrigation', 'harvest', 'mandi', 'price', 'weather', 'monsoon',
            'drought', 'rain', 'yield', 'pesticide', 'organic', 'scheme',
            'subsidy', 'loan', 'insurance', 'krishi', 'kisan', 'बीज', 'खाद'
        ]
        
        # Check for agriculture keywords
        for keyword in agriculture_keywords:
            if keyword in text_lower:
                return True
        
        # Check for crop names
        crop_keywords = [
            'rice', 'wheat', 'cotton', 'sugarcane', 'maize', 'paddy',
            'groundnut', 'soybean', 'pulses', 'oilseeds', 'vegetables',
            'fruits', 'millets', 'jowar', 'bajra', 'ragi'
        ]
        
        for crop in crop_keywords:
            if crop in text_lower:
                return True
        
        return False
    
    def _categorize_news(self, text: str) -> str:
        """Categorize news based on content"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['price', 'mandi', 'market', 'rate', 'export']):
            return "market"
        elif any(word in text_lower for word in ['weather', 'rain', 'monsoon', 'drought', 'flood']):
            return "weather"
        elif any(word in text_lower for word in ['disease', 'pest', 'insect', 'spray', 'chemical']):
            return "pest"
        elif any(word in text_lower for word in ['scheme', 'subsidy', 'loan', 'government', 'policy']):
            if any(word in text_lower for word in ['policy', 'bill', 'regulation']):
                return "policy"
            return "government"
        elif any(word in text_lower for word in ['crop', 'seed', 'yield', 'harvest', 'cultivation', 'farming']):
            return "crop"
        else:
            return "crop"
    
    def _calculate_importance(self, title: str) -> str:
        """Calculate importance level of news"""
        title_lower = title.lower()
        
        high_importance = ['emergency', 'alert', 'warning', 'crisis', 'disaster']
        medium_importance = ['important', 'major', 'breakthrough', 'new', 'launch']
        
        for word in high_importance:
            if word in title_lower:
                return "high"
        
        for word in medium_importance:
            if word in title_lower:
                return "medium"
        
        return "low"
    
    def _deduplicate_news(self, news_items: List[Dict]) -> List[Dict]:
        """Remove duplicate news items"""
        seen_titles = set()
        unique_news = []
        
        for item in news_items:
            title = item.get('title', '').strip().lower()
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(item)
        
        return unique_news

    def _attach_display_fields(self, item: Dict) -> Dict:
        """Attach frontend-friendly fields like image_url and important flag."""
        category = str(item.get("category", "general")).lower()
        title = str(item.get("title", ""))
        importance = str(item.get("importance", "low")).lower()

        if not item.get("date"):
            item["date"] = ""

        if not item.get("summary") and item.get("description"):
            item["summary"] = item.get("description")

        item["is_important"] = importance == "high" or category in {"weather", "market", "disease", "government"}

        # Keep deterministic category image so cards always have visuals.
        category_images = {
            "market": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=1200&auto=format&fit=crop",
            "weather": "https://images.unsplash.com/photo-1464195244916-405fa0a82545?w=1200&auto=format&fit=crop",
            "disease": "https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=1200&auto=format&fit=crop",
            "government": "https://images.unsplash.com/photo-1464979834326-b695d5f4c9ce?w=1200&auto=format&fit=crop",
            "technology": "https://images.unsplash.com/photo-1574943320219-553eb213f72d?w=1200&auto=format&fit=crop",
            "organic": "https://images.unsplash.com/photo-1464226184884-fa280b87c399?w=1200&auto=format&fit=crop",
            "general": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1200&auto=format&fit=crop",
        }

        image_url = item.get("image_url")
        if not image_url and self.enable_remote_image_fetch:
            query = " ".join([word for word in [title, category, "agriculture"] if word])
            image_url = self._get_image_for_query(query)
        item["image_url"] = image_url or category_images.get(category, category_images["general"])
        item["slug"] = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return item

    def _get_image_for_query(self, query: str) -> str:
        """Fetch a relevant image URL using free image APIs."""
        if not query:
            return ""

        cache_key = query.lower().strip()
        cached = self.image_cache.get(cache_key)
        if cached:
            url, timestamp = cached
            if datetime.now().timestamp() - timestamp < self.image_cache_timeout:
                return url

        # Try Pexels
        pexels_key = os.getenv("PEXELS_API_KEY")
        if pexels_key:
            try:
                res = requests.get(
                    "https://api.pexels.com/v1/search",
                    headers={"Authorization": pexels_key},
                    params={"query": query, "per_page": 1, "orientation": "landscape"},
                    timeout=8
                )
                if res.status_code == 200:
                    data = res.json()
                    photo = (data.get("photos") or [None])[0]
                    if photo and photo.get("src", {}).get("large"):
                        url = photo["src"]["large"]
                        self.image_cache[cache_key] = (url, datetime.now().timestamp())
                        return url
            except Exception as e:
                logger.warning(f"Pexels image error: {str(e)}")

        # Try Unsplash
        unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
        if unsplash_key:
            try:
                res = requests.get(
                    "https://api.unsplash.com/search/photos",
                    headers={"Authorization": f"Client-ID {unsplash_key}"},
                    params={"query": query, "per_page": 1, "orientation": "landscape"},
                    timeout=8
                )
                if res.status_code == 200:
                    data = res.json()
                    photo = (data.get("results") or [None])[0]
                    if photo and photo.get("urls", {}).get("regular"):
                        url = photo["urls"]["regular"]
                        self.image_cache[cache_key] = (url, datetime.now().timestamp())
                        return url
            except Exception as e:
                logger.warning(f"Unsplash image error: {str(e)}")

        # Try Pixabay
        pixabay_key = os.getenv("PIXABAY_API_KEY")
        if pixabay_key:
            try:
                res = requests.get(
                    "https://pixabay.com/api/",
                    params={"key": pixabay_key, "q": query, "image_type": "photo", "per_page": 3},
                    timeout=8
                )
                if res.status_code == 200:
                    data = res.json()
                    hit = (data.get("hits") or [None])[0]
                    if hit and hit.get("largeImageURL"):
                        url = hit["largeImageURL"]
                        self.image_cache[cache_key] = (url, datetime.now().timestamp())
                        return url
            except Exception as e:
                logger.warning(f"Pixabay image error: {str(e)}")

        self.image_cache[cache_key] = ("", datetime.now().timestamp())
        return ""
    
    def get_news_for_farmers(self, location: str = None, crop: str = None) -> List[Dict]:
        """Get news filtered for specific farmer context"""
        try:
            all_news = self.get_agriculture_news(limit=20)
            
            # Filter based on location and crop
            filtered_news = []
            
            for news_item in all_news:
                title = news_item.get('title', '').lower()
                summary = news_item.get('summary', '').lower()
                text = title + " " + summary
                
                # Location filter
                location_match = True
                if location:
                    location_lower = location.lower()
                    location_match = location_lower in text
                
                # Crop filter
                crop_match = True
                if crop:
                    crop_lower = crop.lower()
                    crop_match = crop_lower in text
                
                if location_match and crop_match:
                    filtered_news.append(news_item)
            
            # If no filtered news, return general agriculture news
            if not filtered_news:
                return all_news[:10]
            
            return filtered_news[:10]
            
        except Exception as e:
            logger.error(f"Error getting farmer news: {str(e)}")
            raise APIError("News service unavailable", 503)
    
    def get_news_summary(self) -> Dict:
        """Get summary of today's agriculture news"""
        try:
            news_items = self.get_agriculture_news(limit=5)
            
            # Categorize news
            categories = {}
            for item in news_items:
                category = item.get('category', 'general')
                if category not in categories:
                    categories[category] = []
                categories[category].append(item.get('title', ''))
            
            # Generate summary text
            summary_parts = []
            if 'market' in categories:
                summary_parts.append(f"Market updates: {len(categories['market'])} news items")
            if 'weather' in categories:
                summary_parts.append(f"Weather alerts: {len(categories['weather'])} updates")
            if 'government' in categories:
                summary_parts.append(f"Government schemes: {len(categories['government'])} announcements")
            
            summary = ". ".join(summary_parts) if summary_parts else "Regular agriculture news today"
            
            return {
                "date": datetime.now().strftime('%Y-%m-%d'),
                "total_news": len(news_items),
                "summary": summary,
                "categories": {k: len(v) for k, v in categories.items()},
                "top_headlines": [item.get('title', '') for item in news_items[:3]]
            }
            
        except Exception as e:
            logger.error(f"Error getting news summary: {str(e)}")
            raise APIError("News service unavailable", 503)
    
    def _get_fallback_news(self, limit: int) -> List[Dict]:
        """[DEPRECATED] Only returns empty list to enforce real data policy"""
        return []
    
    def _filter_allowed_news(self, items: List[Dict]) -> List[Dict]:
        allowed = []
        for item in items or []:
            title = str(item.get("title", "")).lower()
            summary = str(item.get("summary", "")).lower()
            text_blob = f"{title} {summary}"
            if any(blocked in text_blob for blocked in self.blocked_keywords):
                continue

            category = str(item.get("category", "")).lower().strip()
            if category not in self.allowed_categories:
                category = self._categorize_news(text_blob)
                item["category"] = category

            if category in self.allowed_categories:
                allowed.append(item)
        return allowed

    def _parse_iso_datetime(self, value: str) -> Optional[datetime]:
        try:
            if not value:
                return None
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    def clear_cache(self):
        """Clear news cache"""
        self.cache.clear()
        try:
            db_service.delete_many("news_cache", {"cache_type": "agriculture_news"})
        except Exception:
            pass
        logger.info("News cache cleared")
