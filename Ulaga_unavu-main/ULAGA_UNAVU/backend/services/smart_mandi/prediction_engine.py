from typing import Dict, List
import statistics

class PredictionEngine:
    def _moving_average(self, values: List[float], window: int) -> List[float]:
        if not values:
            return []
        ma = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            window_vals = values[start:i+1]
            ma.append(sum(window_vals) / len(window_vals))
        return ma

    def _trend_slope(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        return (values[-1] - values[0]) / max(1, len(values) - 1)

    def _confidence(self, values: List[float]) -> float:
        if len(values) < 2:
            return 40.0
        try:
            stdev = statistics.stdev(values)
            mean = statistics.mean(values)
            if mean == 0:
                return 40.0
            volatility = min(1.0, stdev / mean)
            return round(100 - (volatility * 60), 2)
        except Exception:
            return 45.0

    def generate_forecasts(self, series: List[Dict]) -> Dict:
        if not series:
            return {
                "error": "No series data",
                "forecasts": [],
                "moving_average": [],
                "trend": "STABLE",
                "confidence": 40
            }

        values = [float(item.get('modal_price', 0)) for item in series if item.get('modal_price') is not None]
        if not values:
            return {
                "error": "No series data",
                "forecasts": [],
                "moving_average": [],
                "trend": "STABLE",
                "confidence": 40
            }

        ma7 = self._moving_average(values, 7)
        slope = self._trend_slope(values[-10:] if len(values) >= 10 else values)
        trend = "UP" if slope > 0 else "DOWN" if slope < 0 else "STABLE"
        confidence = self._confidence(values[-15:] if len(values) >= 15 else values)

        last = values[-1]
        forecasts = []
        for days in [7, 15, 30]:
            projected = last + (slope * days)
            forecasts.append({
                "days": days,
                "price": round(max(0, projected), 2)
            })

        return {
            "forecasts": forecasts,
            "moving_average": [round(x, 2) for x in ma7],
            "trend": trend,
            "confidence": confidence
        }
