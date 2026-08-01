import json
from datetime import datetime
from typing import Dict, List
from utils.path_utils import get_dataset_path

class MarketHistoryStorage:
    def __init__(self):
        self.path = get_dataset_path('market_history.json')

    def _read(self) -> List[Dict]:
        try:
            with open(self.path, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _write(self, data: List[Dict]):
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)

    def append_daily_price(self, crop: str, state: str, district: str, payload: Dict):
        data = self._read()
        today = datetime.utcnow().strftime('%Y-%m-%d')
        current_price = None
        if payload.get('prices'):
            current_price = payload['prices'][0].get('modal_price')
        if current_price is None:
            return
        record = {
            "date": today,
            "crop": crop,
            "state": state,
            "district": district or 'All',
            "modal_price": current_price
        }
        data.append(record)
        self._write(data[-365:])

    def get_history(self, crop: str, state: str, district: str) -> List[Dict]:
        data = self._read()
        result = []
        for item in data:
            if item.get('crop', '').lower() == crop.lower() and item.get('state') == state:
                if not district or item.get('district') == district:
                    result.append(item)
        return result[-90:]
