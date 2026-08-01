import logging
from datetime import datetime
from typing import Dict, List
from services.market_service import MarketService

logger = logging.getLogger(__name__)

class PriceFetcher:
    def __init__(self):
        self.market_service = MarketService()

    def get_current_prices(self, crop: str, state: str, district: str) -> Dict:
        prices = self.market_service.get_mandi_prices(crop, state, district)
        used_curated_fallback = False
        if prices.get('error'):
            # Second chance: curated dataset fallback with alias matching.
            fallback = self.market_service._get_prices_from_database(crop, state, district)
            if fallback.get("prices"):
                prices = fallback
                used_curated_fallback = True
            else:
                return {"error": prices.get('error')}

        series = []
        if not used_curated_fallback:
            series_payload = self.market_service.get_mandi_timeseries(crop, state, district)
            series = series_payload.get('series', [])

        latest = prices.get('prices', [])
        return {
            "crop": prices.get('crop', crop),
            "state": prices.get('state', state),
            "district": prices.get('district', district),
            "prices": latest,
            "series": series,
            "source": prices.get('source', 'Government Mandi API'),
            "updated_at": datetime.utcnow().isoformat()
        }

    def get_series(self, crop: str, state: str, district: str, days: int = 30) -> List[Dict]:
        payload = self.market_service.get_mandi_timeseries(crop, state, district, days=days)
        return payload.get('series', [])
