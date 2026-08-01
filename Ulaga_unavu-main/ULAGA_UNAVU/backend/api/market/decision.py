"""
Market decision engine for ULAGA_UNAVU
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from services.market_service import MarketService
from services.local_storage import db_service
from services.llm_service import LLMService
from utils.date_utils import calculate_days_remaining

logger = logging.getLogger(__name__)

class MarketDecisionEngine:
    """Engine for making market decisions"""
    
    def __init__(self):
        self.market_service = MarketService()
        self.db_service = db_service
        self.llm_service = LLMService()
        
    def get_mandi_prices(self, crop_name: str, state: str = "Tamil Nadu", district: str = None) -> Dict:
        """Get mandi prices for crop"""
        return self.market_service.get_mandi_prices(crop_name, state, district)
    
    def get_broker_prices(self, crop_name: str, district: str) -> Dict:
        """Get broker prices for crop"""
        return self.market_service.get_broker_prices(crop_name, district)
    
    def get_market_decision(self, user_id: str, crop_name: str, quantity: float, 
                           harvest_date: str, storage_type: str, location: str, lang: str = "en") -> Dict:
        """Get comprehensive market decision with localized reasoning"""
        try:
            # Get price data
            mandi_data = self.get_mandi_prices(crop_name, "Tamil Nadu", location)
            broker_data = self.get_broker_prices(crop_name, location)
            if mandi_data.get("error"):
                return {
                    "error": mandi_data.get("error", "Real-time market prices unavailable"),
                    "status_code": int(mandi_data.get("status_code", 503)),
                    "crop": crop_name
                }
            
            # Calculate shelf life risk
            shelf_life = self.calculate_shelf_life_risk(crop_name, harvest_date, storage_type)
            
            # Analyze live price trend
            live_market = self.market_service.get_crop_market_data(crop_name, location, "Tamil Nadu")
            if live_market.get("error"):
                return {
                    "error": live_market.get("error", "Real-time market prices unavailable"),
                    "status_code": int(live_market.get("status_code", 503)),
                    "crop": crop_name
                }
            current_live = float(live_market.get("current_price", 0) or 0)
            avg_live = float(live_market.get("seven_day_avg", 0) or 0)
            change_percent = ((current_live - avg_live) / avg_live) * 100 if avg_live else 0
            price_trend = {
                "trend": live_market.get("trend", "STABLE"),
                "change_percent": round(change_percent, 2)
            }
            
            # Get mandi price
            mandi_price = 0
            if mandi_data and mandi_data.get('prices'):
                mandi_price = mandi_data['prices'][0].get('modal_price', 0)
            
            # Get broker price
            broker_price = broker_data.get('broker_price', 0)
            
            # Make decision
            decision_result = self._make_decision(
                crop_name=crop_name,
                mandi_price=mandi_price,
                broker_price=broker_price,
                shelf_life=shelf_life,
                price_trend=price_trend,
                quantity=quantity,
                lang=lang
            )
            
            # Calculate expected value
            expected_value = self._calculate_expected_value(
                decision=decision_result['decision'],
                mandi_price=mandi_price,
                broker_price=broker_price,
                quantity=quantity,
                price_trend=price_trend,
                transport_cost=mandi_price * 0.05  # 5% transport cost
            )
            
            # Build response
            response = {
                "user_id": user_id,
                "crop": crop_name,
                "quantity": quantity,
                "harvest_date": harvest_date,
                "storage_type": storage_type,
                "location": location,
                "decision": decision_result['decision'],
                "reasoning": decision_result['reasoning'],
                "confidence": decision_result['confidence'],
                "prices": {
                    "mandi": mandi_price,
                    "broker": broker_price,
                    "difference": mandi_price - broker_price
                },
                "shelf_life": shelf_life,
                "price_trend": price_trend,
                "expected_value": expected_value,
                "recommended_action": self._get_recommended_action(decision_result['decision'], lang=lang),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Market decision error: {str(e)}")
            return {
                "error": "Market decision unavailable due to missing real-time price data",
                "status_code": 503,
                "crop": crop_name
            }

    def get_market_snapshot(self, user_id: str, crop_name: str, state: str, district: str, lang: str = "en") -> Dict:
        """Get market snapshot with recommendation based on live mandi data."""
        try:
            snapshot = self.market_service.get_mandi_snapshot(crop_name, state, district)
            if snapshot.get("error"):
                return snapshot

            decision = self._make_snapshot_decision(snapshot)
            recommendation = self._generate_snapshot_recommendation(snapshot, decision, lang)

            snapshot["recommendation"] = recommendation
            snapshot["decision"] = decision
            snapshot["user_id"] = user_id
            return snapshot
        except Exception as e:
            logger.error(f"Market snapshot error: {str(e)}")
            return {"error": "Market snapshot unavailable", "crop": crop_name, "status_code": 503}

    def _make_snapshot_decision(self, snapshot: Dict) -> Dict:
        trend = snapshot.get("trend", "STABLE")
        day_change = snapshot.get("day_change_percent", snapshot.get("change_percent", 0)) or 0
        window_change = snapshot.get("window_change_percent")

        # Prefer 10-20 day window if available
        if window_change is not None:
            if window_change <= -2:
                return {"status": "SELL", "label": "SELL NOW", "color": "red"}
            if window_change >= 2:
                return {"status": "WAIT", "label": "WAIT", "color": "green"}
            return {"status": "HOLD", "label": "HOLD", "color": "yellow"}

        if trend == "DOWN" and day_change < -1:
            return {"status": "SELL", "label": "SELL NOW", "color": "red"}
        if trend == "UP" and day_change > 1:
            return {"status": "WAIT", "label": "WAIT", "color": "green"}
        return {"status": "HOLD", "label": "HOLD", "color": "yellow"}

    def _generate_snapshot_recommendation(self, snapshot: Dict, decision: Dict, lang: str) -> Dict:
        """Generate short, clean recommendation + factors."""
        factors = []
        trend = snapshot.get("trend", "STABLE")
        change = snapshot.get("day_change_percent", snapshot.get("change_percent", 0)) or 0
        week_change = snapshot.get("week_change_percent")
        window_change = snapshot.get("window_change_percent")
        window_days = snapshot.get("window_days", 14)
        if trend == "UP":
            factors.append("Prices trending upward")
        elif trend == "DOWN":
            factors.append("Prices trending downward")
        else:
            factors.append("Prices stable")
        if window_change is not None:
            factors.append(f"Last {window_days} days: {window_change}%")
        if week_change is not None:
            factors.append(f"Weekly change: {week_change}%")

        prompt = f"""
        You are an agriculture market analyst.
        Provide a short, 2-line recommendation for a farmer.
        Crop: {snapshot.get('crop')}
        Current price: {snapshot.get('current_price')}
        Change today: {change}%
        Trend: {trend}
        {f"Last {window_days} days change: {window_change}%" if window_change is not None else ""}
        Decision: {decision.get('status')}
        Language: {'Tamil' if lang == 'ta' else 'English'}
        Keep it short and simple.
        """

        summary = None
        try:
            summary = self.llm_service.generate_response(prompt, max_tokens=80)
        except Exception:
            summary = None

        if not summary:
            summary = f"{decision.get('label')}: prices are {trend.lower()} ({change}%)."

        return {
            "summary": summary.strip(),
            "factors": factors[:4]
        }
    
    def calculate_shelf_life_risk(self, crop_name: str, harvest_date: str, storage_type: str) -> Dict:
        """Calculate shelf life risk"""
        return self.market_service._calculate_shelf_life_risk(crop_name, harvest_date, storage_type)
    
    def analyze_price_trend(self, crop_name: str) -> Dict:
        """Analyze price trend for crop"""
        return self.market_service._analyze_price_trend(crop_name)
    
    def _make_decision(self, crop_name: str, mandi_price: float, broker_price: float,
                      shelf_life: Dict, price_trend: Dict, quantity: float, lang: str = "en") -> Dict:
        """Make SELL/WAIT decision with localized reasoning"""
        
        risk_level = shelf_life.get('risk_level', 'Low')
        days_remaining = shelf_life.get('days_remaining', 30)
        trend = price_trend.get('trend', 'STABLE')
        change_percent = price_trend.get('change_percent', 0)
        
        reasoning = []
        confidence = 0.7  # Base confidence
        
        # Rule 1: Critical shelf life risk
        if risk_level == "Critical":
            decision = "SELL"
            reasoning.append(f"Critical shelf life risk ({days_remaining} days remaining)")
            confidence = 0.9
        
        # Rule 2: High shelf life risk
        elif risk_level == "High":
            decision = "SELL"
            reasoning.append(f"High shelf life risk ({days_remaining} days remaining)")
            confidence = 0.8
        
        # Rule 3: Medium risk with downward trend
        elif risk_level == "Medium" and trend == "DOWN":
            decision = "SELL"
            reasoning.append(f"Medium shelf life risk with downward price trend ({change_percent:.1f}% decrease)")
            confidence = 0.75
        
        # Rule 4: Broker better than mandi (considering transport)
        elif self._is_broker_better(mandi_price, broker_price):
            decision = "SELL_TO_BROKER"
            price_diff = mandi_price - broker_price
            reasoning.append(f"Broker price is better considering transport savings (₹{price_diff:.0f} difference)")
            confidence = 0.8
        
        # Rule 5: Upward trend with low risk
        elif trend == "UP" and risk_level == "Low":
            decision = "WAIT"
            reasoning.append(f"Prices trending upward ({change_percent:.1f}% increase) with low shelf life risk")
            confidence = 0.7
        
        # Rule 6: Large quantity
        elif quantity > 1000:  # More than 1000 quintals
            decision = "SELL_IN_PARTS"
            reasoning.append(f"Large quantity ({quantity} quintals) - selling in parts reduces market impact")
            confidence = 0.6
        
        # Default: Conservative SELL
        else:
            decision = "SELL"
            reasoning.append("Conservative approach - current prices are reasonable")
            confidence = 0.6
        
        # Add trend info
        if trend != "STABLE":
            reasoning.append(f"Price trend: {trend} ({change_percent:.1f}%)")
        
        return {
            "decision": decision,
            "reasoning": self._generate_localized_reasoning(decision, reasoning, lang),
            "confidence": confidence
        }
    
    def _generate_localized_reasoning(self, decision: str, points: List[str], lang: str = "en") -> List[str]:
        """Generate localized reasoning using LLM"""
        try:
            language_name = "Tamil" if lang == "ta" else "English"
            points_str = "\n".join([f"- {p}" for p in points])
            prompt = f"""
            As a market analyst, convert these technical points into 2-3 farmer-friendly sentences in {language_name}.
            
            Decision: {decision}
            Points:
            {points_str}
            """
            response = self.llm_service.generate_response(prompt, max_tokens=150)
            return [response.strip()]
        except:
            return points

    def _is_broker_better(self, mandi_price: float, broker_price: float) -> bool:
        """Check if broker price is better considering transport"""
        if mandi_price <= 0 or broker_price <= 0:
            return False
        
        # Effective mandi price after 5% transport cost
        effective_mandi = mandi_price * 0.95
        
        # Broker is better if price is within 2% of effective mandi price
        return broker_price > effective_mandi * 0.98
    
    def _calculate_expected_value(self, decision: str, mandi_price: float, broker_price: float,
                                quantity: float, price_trend: Dict, transport_cost: float) -> Dict:
        """Calculate expected value for different decisions"""
        
        trend = price_trend.get('trend', 'STABLE')
        change_percent = price_trend.get('change_percent', 0)
        
        # Future price prediction
        if trend == "UP":
            future_price = mandi_price * (1 + (change_percent / 100) * 0.3)  # Conservative
        elif trend == "DOWN":
            future_price = mandi_price * (1 - (change_percent / 100) * 0.3)
        else:
            future_price = mandi_price
        
        # Calculate values
        values = {
            "sell_now_mandi": mandi_price * quantity,
            "sell_now_broker": broker_price * quantity,
            "sell_future": future_price * quantity,
            "transport_cost": transport_cost * quantity,
            "effective_mandi": (mandi_price * quantity) - (transport_cost * quantity),
            "effective_broker": broker_price * quantity,
            "best_option": "BROKER" if broker_price > (mandi_price - transport_cost) else "MANDI"
        }
        
        # Round values
        for key in values:
            if isinstance(values[key], (int, float)):
                values[key] = round(values[key], 2)
        
        return values
    
    def _get_recommended_action(self, decision: str, lang: str = "en") -> str:
        """Get localized recommended action using LLM"""
        try:
            language_name = "Tamil" if lang == "ta" else "English"
            prompt = f"Provide a direct, 1-sentence action recommendation for a farmer in {language_name} based on the market decision: {decision}."
            response = self.llm_service.generate_response(prompt, max_tokens=100)
            return response.strip()
        except:
            actions = {
                "SELL": "Sell immediately at nearest mandi",
                "WAIT": "Store properly and wait for better prices",
                "SELL_TO_BROKER": "Contact local broker for immediate sale",
                "SELL_IN_PARTS": "Sell 50% now, 50% in next 7 days",
                "DO NOT SELL": "Hold produce - prices expected to drop further",
                "HOLD": "Monitor prices daily - be ready to sell"
            }
            return actions.get(decision, "Consult local market expert")
    
    def _get_fallback_decision(self, crop_name: str, quantity: float, harvest_date: str) -> Dict:
        """Get fallback decision when analysis fails"""
        return {
            "error": "Market decision unavailable due to missing real-time price data",
            "status_code": 503,
            "crop": crop_name
        }
