import json
from typing import Dict
from services.weather_service import WeatherService
from services.llm_service import LLMService
from utils.path_utils import get_dataset_path

class SellScoreEngine:
    def __init__(self):
        self.weather_service = WeatherService()
        self.llm = LLMService()
        self.msp_data = self._load_msp_data()

    def _load_msp_data(self):
        path = get_dataset_path('msp_data.json')
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _msp_for_crop(self, crop: str):
        return self.msp_data.get(crop.lower())

    def generate_sell_score(self, crop: str, price_payload: Dict, prediction: Dict, location: Dict) -> Dict:
        prices = price_payload.get('prices', [])
        current_price = None
        arrivals = None
        if prices:
            current_price = prices[0].get('modal_price')
            arrivals = prices[0].get('arrivals')

        msp = self._msp_for_crop(crop)
        msp_gap = None
        if msp and current_price:
            try:
                msp_gap = round(((current_price - msp) / msp) * 100, 2)
            except Exception:
                msp_gap = None

        trend = prediction.get('trend', 'STABLE')
        confidence = prediction.get('confidence', 40)

        score = 50
        if trend == 'UP':
            score += 12
        elif trend == 'DOWN':
            score -= 12

        if msp_gap is not None:
            if msp_gap < 0:
                score -= 10
            elif msp_gap > 5:
                score += 10

        if arrivals:
            try:
                if float(arrivals) > 200:
                    score -= 6
                elif float(arrivals) < 50:
                    score += 6
            except Exception:
                pass

        # Weather impact (simple proxy)
        weather = None
        try:
            district = location.get('district') or 'Tamil Nadu'
            weather = self.weather_service.get_current_weather(district)
        except Exception:
            weather = None

        weather_impact = 'neutral'
        if weather and not weather.get('error'):
            temp = weather.get('temperature') or weather.get('temp')
            if temp and temp > 34:
                score -= 4
                weather_impact = 'hot'
            elif temp and temp < 18:
                score += 2
                weather_impact = 'cool'

        score = max(0, min(100, score))
        label = 'HOLD'
        if score >= 80:
            label = 'STRONG SELL'
        elif score >= 65:
            label = 'SELL'
        elif score >= 45:
            label = 'HOLD'
        else:
            label = 'WAIT'

        return {
            "score": score,
            "label": label,
            "trend": trend,
            "confidence": confidence,
            "msp": msp,
            "msp_gap_percent": msp_gap,
            "weather_impact": weather_impact,
            "arrivals": arrivals
        }

    def generate_tamil_recommendation(self, score_payload: Dict, lang: str = 'ta') -> Dict:
        language_code = str(lang or 'en').strip().lower()
        language_name = 'Tamil' if language_code == 'ta' else 'English'
        output_instruction = (
            "Reply in simple Tamil."
            if language_code == 'ta'
            else "Reply in simple English."
        )
        prompt = f"""
        You are an agriculture advisor. {output_instruction}
        Current Sell Score: {score_payload.get('score')}
        Decision: {score_payload.get('label')}
        Trend: {score_payload.get('trend')}
        MSP Gap: {score_payload.get('msp_gap_percent')}
        Weather impact: {score_payload.get('weather_impact')}
        Provide 2-3 short sentences: current condition, risk level, suggested action, time to sell in days.
        """
        try:
            response = self.llm.generate_response(
                prompt,
                max_tokens=120,
                temperature=0.3,
                language='tamil' if language_code == 'ta' else 'english'
            )
            return {"text": response.strip()}
        except Exception:
            if language_code == 'ta':
                return {"text": "நேரடி சந்தை தரவு கிடைக்கவில்லை. பின்னர் மீண்டும் சரிபார்க்கவும்."}
            return {"text": "Live mandi data is currently unavailable. Please check again later."}
