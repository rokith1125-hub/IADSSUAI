"""
Market service for agricultural price data
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os
import csv
import re
import math
from io import StringIO
from utils.path_utils import get_dataset_path

logger = logging.getLogger(__name__)

class MarketService:
    """Service for agricultural market data operations"""
    
    def __init__(self):
        self.base_url = "https://api.data.gov.in/resource"
        self.cache = {}
        self.cache_timeout = 3600  # 1 hour for market data
        self.timeseries_cache = {}
        self.timeseries_cache_timeout = 1800  # 30 minutes for time series
        self.request_timeout_seconds = max(1.5, float(os.getenv("MARKET_API_TIMEOUT_SECONDS", "2.5") or 2.5))
        self.max_alias_attempts = max(1, int(os.getenv("MARKET_MAX_ALIAS_ATTEMPTS", "1") or 1))
        
        # Load crop price database
        self.price_database = self._load_price_database()
        
    def _load_price_database(self) -> Dict:
        """Load crop price database from JSON"""
        try:
            dataset_path = get_dataset_path('market_data.json')
            if os.path.exists(dataset_path):
                with open(dataset_path, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading market dataset: {str(e)}")
            return []
    
    def get_mandi_prices(self, crop_name: str, state: str = "Tamil Nadu", district: str = None) -> Dict:
        """Get mandi prices for crop from government API"""
        cache_key = f"mandi_{crop_name}_{state}_{district}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if datetime.now().timestamp() - timestamp < self.cache_timeout:
                logger.info(f"Using cached mandi prices for {crop_name}")
                return cached_data
        
        try:
            # Try government API first
            api_key = os.getenv('AGMARKNET_API_KEY', '') or os.getenv('DATA_GOV_API_KEY', '')
            if not api_key:
                return self._get_fallback_prices(crop_name, state, district)

            for commodity in self._get_crop_aliases(crop_name)[: self.max_alias_attempts]:
                # 1) Try with district
                params = {
                    'api-key': api_key,
                    'format': 'json',
                    'filters[commodity]': commodity,
                    'filters[state]': state,
                    'limit': 10
                }
                
                if district:
                    params['filters[district]'] = district
                
                response = requests.get(
                    f"{self.base_url}/9ef84268-d588-465a-a308-a864a43d0070",
                    params=params,
                    timeout=self.request_timeout_seconds
                )
                
                if response.status_code == 200:
                    data = response.json()
                    prices = self._process_mandi_response(data)
                    
                    if prices:
                        result = {
                            "source": "Government Mandi API",
                            "crop": commodity,
                            "state": state,
                            "district": district or "All",
                            "prices": prices,
                            "updated_at": datetime.now().isoformat()
                        }
                        
                        self.cache[cache_key] = (result, datetime.now().timestamp())
                        return result

                # 2) Retry without district if nothing found
                if district:
                    params.pop('filters[district]', None)
                    response = requests.get(
                        f"{self.base_url}/9ef84268-d588-465a-a308-a864a43d0070",
                        params=params,
                        timeout=self.request_timeout_seconds
                    )
                    if response.status_code == 200:
                        data = response.json()
                        prices = self._process_mandi_response(data)
                        if prices:
                            result = {
                                "source": "Government Mandi API",
                                "crop": commodity,
                                "state": state,
                                "district": "All",
                                "prices": prices,
                                "updated_at": datetime.now().isoformat()
                            }
                            self.cache[cache_key] = (result, datetime.now().timestamp())
                            return result

            return self._get_fallback_prices(crop_name, state, district)
            
        except Exception as e:
            logger.error(f"Error getting mandi prices: {str(e)}")
            return self._get_fallback_prices(crop_name, state, district)
    
    def _process_mandi_response(self, api_data: Dict) -> List[Dict]:
        """Process government mandi API response with per-market trend."""
        try:
            records = api_data.get('records', []) or []
            if not records:
                return []

            # Group by market + district for latest comparison
            grouped = {}
            for record in records:
                market = record.get('market', 'Unknown')
                district = record.get('district', 'Unknown')
                key = f"{market}||{district}"
                date_obj = self._parse_date(record.get('arrival_date', '') or record.get('date', '') or '')
                grouped.setdefault(key, []).append((date_obj, record))

            items = []
            for key, entries in grouped.items():
                entries.sort(key=lambda x: x[0] or datetime.min, reverse=True)
                latest = entries[0][1]
                prev = entries[1][1] if len(entries) > 1 else None

                latest_modal = self._safe_float(latest.get('modal_price')) or 0
                prev_modal = self._safe_float(prev.get('modal_price')) if prev else None
                change_percent = 0.0
                trend = "STABLE"
                if prev_modal and prev_modal > 0:
                    change_percent = round(((latest_modal - prev_modal) / prev_modal) * 100, 2)
                    if latest_modal > prev_modal:
                        trend = "UP"
                    elif latest_modal < prev_modal:
                        trend = "DOWN"

                items.append({
                    "market": latest.get('market', 'Unknown'),
                    "district": latest.get('district', 'Unknown'),
                    "modal_price": latest.get('modal_price', 0),
                    "min_price": latest.get('min_price', 0),
                    "max_price": latest.get('max_price', 0),
                    "arrivals": latest.get('arrivals_tonnes', 0),
                    "date": latest.get('arrival_date', '') or latest.get('date', ''),
                    "trend": trend,
                    "change_percent": change_percent
                })

            # Sort by price (high to low) and return top 5 as requested in Master Audit
            items.sort(key=lambda x: self._safe_float(x.get("modal_price")) or 0.0, reverse=True)
            return items[:5]
        except Exception as e:
            logger.error(f"Error processing mandi response: {str(e)}")
            return []
    
    def _get_prices_from_database(self, crop_name: str, state: str, district: str = None) -> Dict:
        """Get prices from local database"""
        try:
            crop_data = self._find_crop_in_database(crop_name)
            if not crop_data:
                return self._get_fallback_prices(crop_name, state, district)

            base_price = crop_data.get('base_price', crop_data.get('modal_price'))
            if base_price is None:
                return self._get_fallback_prices(crop_name, state, district)

            major_mandis = crop_data.get("major_mandis") or []
            market_name = district or (major_mandis[0] if major_mandis else f"{state} Mandi")
            canonical_crop = crop_data.get("crop_name") or crop_name

            return {
                "source": "Curated Market Dataset",
                "crop": canonical_crop,
                "state": state,
                "district": district or "All",
                "prices": [{
                    "market": market_name,
                    "district": district or state,
                    "modal_price": float(base_price),
                    "min_price": crop_data.get("min_price"),
                    "max_price": crop_data.get("max_price"),
                    "arrivals": crop_data.get("arrivals"),
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "source": "Curated Market Dataset",
                    "trend": "STABLE",
                    "change_percent": 0.0
                }],
                "updated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting prices from database: {str(e)}")
            return self._get_fallback_prices(crop_name, state, district)
    
    def get_broker_prices(self, crop_name: str, district: str) -> Dict:
        """Get local broker prices from configured live feeds only."""
        try:
            # No curated/hardcoded broker price fallback is allowed.
            return self._get_fallback_broker_prices(crop_name, district)
        except Exception as e:
            logger.error(f"Error getting broker prices: {str(e)}")
            return self._get_fallback_broker_prices(crop_name, district)
    
    def get_market_decision(self, crop_name: str, quantity: float, harvest_date: str, 
                           storage_type: str = "normal") -> Dict:
        """Get market decision (SELL/WAIT) with analysis"""
        try:
            # Get current prices
            mandi_data = self.get_mandi_prices(crop_name, "Tamil Nadu")
            broker_data = self.get_broker_prices(crop_name, "")
            
            if not mandi_data or not mandi_data.get('prices'):
                raise Exception("Could not get price data")
            
            current_price = mandi_data['prices'][0].get('modal_price', 0)
            broker_price = broker_data.get('broker_price', 0)
            
            # Calculate shelf life risk
            shelf_life_risk = self._calculate_shelf_life_risk(crop_name, harvest_date, storage_type)
            
            # Analyze price trend
            price_trend = self._analyze_price_trend(crop_name)
            
            # Make decision
            decision = self._make_sell_decision(
                current_price=current_price,
                broker_price=broker_price,
                shelf_life_risk=shelf_life_risk,
                price_trend=price_trend,
                quantity=quantity
            )
            
            # Calculate expected value
            expected_value = self._calculate_expected_value(
                decision=decision,
                current_price=current_price,
                broker_price=broker_price,
                quantity=quantity,
                price_trend=price_trend
            )
            
            return {
                "crop": crop_name,
                "quantity": quantity,
                "decision": decision,
                "reasoning": self._get_decision_reasoning(decision, shelf_life_risk, price_trend),
                "prices": {
                    "mandi": current_price,
                    "broker": broker_price,
                    "difference": current_price - broker_price
                },
                "shelf_life": shelf_life_risk,
                "price_trend": price_trend,
                "expected_value": expected_value,
                "recommended_action": self._get_recommended_action(decision),
                "updated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting market decision: {str(e)}")
            return self._get_fallback_decision(crop_name, quantity)
    
    def _calculate_shelf_life_risk(self, crop_name: str, harvest_date: str, storage_type: str) -> Dict:
        """Calculate shelf life risk for crop"""
        try:
            # Crop shelf life database
            shelf_life_db = {
                "rice": 365,
                "wheat": 180,
                "cotton": 0,  # Immediate sale
                "sugarcane": 2,
                "groundnut": 180,
                "maize": 90,
                "tomato": 7,
                "onion": 60,
                "potato": 120,
                "millets": 180
            }
            
            # Parse harvest date
            if isinstance(harvest_date, str):
                harvest_date = datetime.fromisoformat(harvest_date.replace('Z', '+00:00'))
            
            days_since_harvest = (datetime.now() - harvest_date).days
            max_shelf_life = shelf_life_db.get(crop_name.lower(), 30)
            
            # Adjust for storage type
            if storage_type == "cold":
                max_shelf_life *= 2
            elif storage_type == "silo":
                max_shelf_life *= 1.5
            
            days_remaining = max_shelf_life - days_since_harvest
            
            # Calculate risk
            if days_remaining <= 0:
                risk = "Critical"
                color = "red"
            elif days_remaining <= 7:
                risk = "High"
                color = "orange"
            elif days_remaining <= 14:
                risk = "Medium"
                color = "yellow"
            else:
                risk = "Low"
                color = "green"
            
            return {
                "days_remaining": max(0, days_remaining),
                "risk_level": risk,
                "color": color,
                "storage_advice": self._get_storage_advice(crop_name, storage_type, days_remaining)
            }
            
        except Exception as e:
            logger.error(f"Error calculating shelf life: {str(e)}")
            return {
                "days_remaining": None,
                "risk_level": "Unknown",
                "color": "gray",
                "storage_advice": "Unable to calculate shelf life with current data"
            }
    
    def _analyze_price_trend(self, crop_name: str) -> Dict:
        """Analyze price trend for crop"""
        try:
            # Get historical data from database
            crop_data = None
            for crop in self.price_database:
                if crop['crop_name'].lower() == crop_name.lower():
                    crop_data = crop
                    break
            
            if crop_data:
                price_trend = crop_data.get('price_trend', {})
                
                # Simple trend analysis
                prices = list(price_trend.values())
                if len(prices) >= 2:
                    recent_price = prices[-1]
                    previous_price = prices[-2]
                    
                    if recent_price > previous_price:
                        trend = "UP"
                        change_percent = ((recent_price - previous_price) / previous_price) * 100
                    elif recent_price < previous_price:
                        trend = "DOWN"
                        change_percent = ((previous_price - recent_price) / previous_price) * 100
                    else:
                        trend = "STABLE"
                        change_percent = 0
                    
                    return {
                        "trend": trend,
                        "change_percent": round(change_percent, 2),
                        "current_season": crop_data.get('typical_season', ''),
                        "demand_peak": crop_data.get('demand_peak', []),
                        "supply_peak": crop_data.get('supply_peak', [])
                    }
            
            return {
                "trend": "UNKNOWN",
                "change_percent": 0,
                "current_season": None,
                "demand_peak": [],
                "supply_peak": []
            }
            
        except Exception as e:
            logger.error(f"Error analyzing price trend: {str(e)}")
            return {"trend": "UNKNOWN", "change_percent": 0}
    
    def _make_sell_decision(self, current_price: float, broker_price: float, 
                           shelf_life_risk: Dict, price_trend: Dict, quantity: float) -> str:
        """Make SELL/WAIT decision"""
        risk_level = shelf_life_risk.get('risk_level', 'Low')
        trend = price_trend.get('trend', 'STABLE')
        
        # Rule 1: Critical shelf life risk - SELL immediately
        if risk_level == "Critical":
            return "SELL"
        
        # Rule 2: High shelf life risk - SELL
        if risk_level == "High":
            return "SELL"
        
        # Rule 3: Medium shelf life risk with downward trend - SELL
        if risk_level == "Medium" and trend == "DOWN":
            return "SELL"
        
        # Rule 4: Broker price better than mandi (considering transport)
        effective_broker_price = broker_price * 1.05  # Add 5% for transport savings
        if effective_broker_price > current_price * 1.02:  # 2% better
            return "SELL_TO_BROKER"
        
        # Rule 5: Upward price trend with low risk - WAIT
        if trend == "UP" and risk_level == "Low":
            return "WAIT"
        
        # Rule 6: Large quantity with stable prices - SELL in parts
        if quantity > 1000 and trend == "STABLE":  # More than 1000 units
            return "SELL_IN_PARTS"
        
        # Default: SELL
        return "SELL"
    
    def _calculate_expected_value(self, decision: str, current_price: float, 
                                broker_price: float, quantity: float, price_trend: Dict) -> Dict:
        """Calculate expected value for different decisions"""
        trend = price_trend.get('trend', 'STABLE')
        change_percent = price_trend.get('change_percent', 0)
        
        # Future price prediction
        if trend == "UP":
            future_price = current_price * (1 + (change_percent / 100) * 0.5)  # Conservative estimate
        elif trend == "DOWN":
            future_price = current_price * (1 - (change_percent / 100) * 0.5)
        else:
            future_price = current_price
        
        # Calculate values
        sell_now_mandi = current_price * quantity
        sell_now_broker = broker_price * quantity
        sell_future = future_price * quantity
        
        # Transportation cost (5% of mandi price)
        transport_cost = current_price * 0.05 * quantity
        
        # Effective values
        effective_mandi = sell_now_mandi - transport_cost
        effective_broker = sell_now_broker  # No transport cost
        
        return {
            "sell_now_mandi": round(sell_now_mandi, 2),
            "sell_now_broker": round(sell_now_broker, 2),
            "sell_future": round(sell_future, 2),
            "effective_mandi": round(effective_mandi, 2),
            "effective_broker": round(effective_broker, 2),
            "transport_cost": round(transport_cost, 2),
            "best_option": "BROKER" if effective_broker > effective_mandi else "MANDI"
        }
    
    def _get_decision_reasoning(self, decision: str, shelf_life_risk: Dict, price_trend: Dict) -> List[str]:
        """Get reasoning for decision"""
        reasoning = []
        
        if decision == "SELL":
            if shelf_life_risk['risk_level'] in ["Critical", "High"]:
                reasoning.append(f"Shelf life risk is {shelf_life_risk['risk_level']} ({shelf_life_risk['days_remaining']} days remaining)")
            reasoning.append("Current prices are favorable")
        elif decision == "WAIT":
            reasoning.append(f"Price trend is {price_trend['trend']} ({price_trend['change_percent']}%)")
            reasoning.append(f"Shelf life risk is {shelf_life_risk['risk_level']}")
            reasoning.append("Expected price increase in coming days")
        elif decision == "SELL_TO_BROKER":
            reasoning.append("Broker price is better considering transport savings")
            reasoning.append("Immediate payment and local convenience")
        elif decision == "SELL_IN_PARTS":
            reasoning.append("Large quantity - selling in parts reduces market impact")
            reasoning.append("Price stability expected")
        
        return reasoning
    
    def _get_recommended_action(self, decision: str) -> str:
        """Get recommended action based on decision"""
        actions = {
            "SELL": "Sell immediately at nearest mandi",
            "WAIT": "Store properly and wait for better prices",
            "SELL_TO_BROKER": "Contact local broker for best deal",
            "SELL_IN_PARTS": "Sell 50% now, 50% next week",
            "DO NOT SELL": "Hold produce - prices expected to drop further"
        }
        return actions.get(decision, "Consult local market expert")
    
    def _get_broker_recommendation(self, broker_price: float, mandi_price: float, transport_saving: float) -> str:
        """Get broker recommendation"""
        effective_price = broker_price + transport_saving
        
        if effective_price > mandi_price * 1.02:
            return "BROKER_BETTER"
        elif effective_price > mandi_price * 0.98:
            return "SIMILAR"
        else:
            return "MANDI_BETTER"
    
    def _get_storage_advice(self, crop_name: str, storage_type: str, days_remaining: int) -> str:
        """Get storage advice"""
        advice = []
        
        if days_remaining < 7:
            advice.append("Immediate sale recommended")
        elif storage_type == "normal":
            advice.append("Store in dry, ventilated area")
            if crop_name.lower() in ["rice", "wheat"]:
                advice.append("Use airtight containers")
        elif storage_type == "cold":
            advice.append("Maintain 10-15°C temperature")
        elif storage_type == "silo":
            advice.append("Monitor for pests regularly")
        
        return ". ".join(advice)
    
    def _get_fallback_prices(self, crop_name: str, state: str, district: str) -> Dict:
        """[DEPRECATED] Only returns empty/error state to enforce real data policy"""
        return {
            "error": "Real-time market prices unavailable",
            "crop": crop_name,
            "prices": [],
            "status_code": 503
        }

    def get_mandi_timeseries(self, crop_name: str, state: str, district: str = None, days: int = 30) -> Dict:
        """Get recent mandi price series for charting."""
        cache_key = f"series_{crop_name}_{state}_{district}_{days}"
        cached = self.timeseries_cache.get(cache_key)
        if cached:
            payload, timestamp = cached
            if datetime.now().timestamp() - timestamp < self.timeseries_cache_timeout:
                return payload

        api_key = os.getenv('AGMARKNET_API_KEY', '') or os.getenv('DATA_GOV_API_KEY', '')
        if not api_key:
            return {"error": "Real-time market prices unavailable", "series": []}

        try:
            for commodity in self._get_crop_aliases(crop_name)[: self.max_alias_attempts]:
                params = {
                    'api-key': api_key,
                    'format': 'json',
                    'filters[commodity]': commodity,
                    'filters[state]': state,
                    'limit': 100,
                    'offset': 0,
                    'sort[arrival_date]': 'desc'
                }
                if district:
                    params['filters[district]'] = district

                response = requests.get(
                    f"{self.base_url}/9ef84268-d588-465a-a308-a864a43d0070",
                    params=params,
                    timeout=self.request_timeout_seconds
                )
                if response.status_code == 200:
                    data = response.json()
                    records = data.get('records', []) or []
                    if not records and district:
                        # retry without district
                        params.pop('filters[district]', None)
                        response = requests.get(
                            f"{self.base_url}/9ef84268-d588-465a-a308-a864a43d0070",
                            params=params,
                            timeout=self.request_timeout_seconds
                        )
                        if response.status_code == 200:
                            data = response.json()
                            records = data.get('records', []) or []

                    if not records:
                        continue

                    series_map = {}
                    for record in records:
                        date_raw = (
                            record.get('arrival_date')
                            or record.get('arrival_date'.upper(), '')
                            or record.get('reported_date')
                            or record.get('timestamp')
                            or record.get('date')
                            or ''
                        )
                        date_obj = self._parse_date(date_raw)
                        if not date_obj:
                            continue
                        date_key = date_obj.strftime('%Y-%m-%d')
                        modal = self._safe_float(record.get('modal_price'))
                        if modal is None:
                            continue
                        series_map.setdefault(date_key, []).append(modal)

                    series = []
                    for date_key, values in series_map.items():
                        series.append({
                            "date": date_key,
                            "modal_price": round(sum(values) / len(values), 2)
                        })

                    series.sort(key=lambda x: x["date"])
                    if days and len(series) > days:
                        series = series[-days:]

                    payload = {"series": series}
                    self.timeseries_cache[cache_key] = (payload, datetime.now().timestamp())
                    return payload

            return {"error": "Real-time market prices unavailable", "series": []}
        except Exception as e:
            logger.error(f"Error fetching mandi series: {str(e)}")
            return {"error": "Real-time market prices unavailable", "series": []}

    def get_mandi_snapshot(self, crop_name: str, state: str, district: str = None) -> Dict:
        """Get a snapshot with current price, range, and trend series."""
        prices = self.get_mandi_prices(crop_name, state, district)
        effective_district = district

        if not effective_district and prices.get("prices"):
            first_district = prices["prices"][0].get("district")
            if first_district and first_district not in ["All", "Unknown"]:
                effective_district = first_district

        series_payload = self.get_mandi_timeseries(crop_name, state, effective_district)
        series = series_payload.get("series", [])

        if prices.get("error") and not series:
            return {"error": "Real-time market prices unavailable", "crop": crop_name, "status_code": 503}

        latest_date = None
        if series:
            latest_date = series[-1]["date"]

        latest_records = []
        if prices.get("prices"):
            latest_records = prices["prices"]

        current_price = None
        if latest_records:
            current_price = self._safe_float(latest_records[0].get("modal_price"))
        elif series:
            current_price = series[-1]["modal_price"]

        range_min = None
        range_max = None
        if latest_records:
            mins = [self._safe_float(r.get("min_price")) for r in latest_records if self._safe_float(r.get("min_price")) is not None]
            maxs = [self._safe_float(r.get("max_price")) for r in latest_records if self._safe_float(r.get("max_price")) is not None]
            range_min = min(mins) if mins else None
            range_max = max(maxs) if maxs else None

        change_percent = 0.0
        trend = "STABLE"
        if len(series) >= 2:
            prev = series[-2]["modal_price"]
            curr = series[-1]["modal_price"]
            if prev:
                change_percent = round(((curr - prev) / prev) * 100, 2)
            if curr > prev:
                trend = "UP"
            elif curr < prev:
                trend = "DOWN"
        elif latest_records and len(latest_records) >= 2:
            # Fallback: use latest two records from mandi list if series too short
            sorted_records = sorted(
                latest_records,
                key=lambda x: self._parse_date(x.get("date", "")) or datetime.min,
                reverse=True
            )
            curr = self._safe_float(sorted_records[0].get("modal_price"))
            prev = self._safe_float(sorted_records[1].get("modal_price"))
            if prev:
                change_percent = round(((curr - prev) / prev) * 100, 2)
                if curr > prev:
                    trend = "UP"
                elif curr < prev:
                    trend = "DOWN"

        week_change = None
        if len(series) >= 8:
            prev_week = series[-8]["modal_price"]
            curr = series[-1]["modal_price"]
            if prev_week:
                week_change = round(((curr - prev_week) / prev_week) * 100, 2)

        window_days = 14
        window_change = None
        if len(series) >= 2:
            window_start_idx = max(0, len(series) - window_days)
            start_price = series[window_start_idx]["modal_price"]
            end_price = series[-1]["modal_price"]
            if start_price:
                window_change = round(((end_price - start_price) / start_price) * 100, 2)

        return {
            "crop": crop_name,
            "state": state,
            "district": effective_district or district or "All",
            "current_price": current_price,
            "range_min": range_min,
            "range_max": range_max,
            "change_percent": change_percent,
            "day_change_percent": change_percent,
            "week_change_percent": week_change,
            "window_days": window_days,
            "window_change_percent": window_change,
            "trend": trend,
            "series": series,
            "markets": latest_records,
            "updated_at": datetime.utcnow().isoformat(),
            "source": prices.get("source", "Government Mandi API")
        }

    def get_crop_market_data(self, crop_name: str, district: str, state: str = "Tamil Nadu") -> Dict:
        """Return real-time market features used by crop scoring."""
        if not crop_name:
            return {
                "available": False,
                "market_score_available": False,
                "error": "Crop name is required",
                "status_code": 400,
            }
        if not district and not state:
            return {
                "available": False,
                "market_score_available": False,
                "error": "District or state context is required",
                "status_code": 400,
            }

        snapshot = self.get_mandi_snapshot(crop_name, state or "Tamil Nadu", district)
        if snapshot.get("error"):
            return {
                "available": False,
                "market_score_available": False,
                "error": snapshot.get("error", "Real-time market prices unavailable"),
                "status_code": int(snapshot.get("status_code", 503)),
            }

        series = snapshot.get("series") or []
        current_price = self._safe_float(snapshot.get("current_price"))
        if current_price is None:
            return {
                "available": False,
                "market_score_available": False,
                "error": "Real-time market prices unavailable",
                "status_code": 503,
            }

        recent_prices: List[float] = []
        for point in series[-7:]:
            value = self._safe_float(point.get("modal_price"))
            if value is not None:
                recent_prices.append(value)

        if not recent_prices:
            recent_prices = [current_price]

        seven_day_avg = sum(recent_prices) / len(recent_prices)
        if len(recent_prices) >= 2:
            mean_value = seven_day_avg
            variance = sum((value - mean_value) ** 2 for value in recent_prices) / len(recent_prices)
            std_dev = math.sqrt(variance)
            volatility_percent = (std_dev / mean_value) * 100 if mean_value else 0.0
        else:
            volatility_percent = 0.0

        trend = snapshot.get("trend", "STABLE")
        return {
            "available": True,
            "market_score_available": True,
            "crop_name": snapshot.get("crop") or crop_name,
            "district": snapshot.get("district") or district,
            "state": snapshot.get("state") or state,
            "current_price": round(current_price, 2),
            "seven_day_avg": round(seven_day_avg, 2),
            "trend": trend,
            "volatility_percent": round(volatility_percent, 2),
            "series_points": len(series),
            "source": snapshot.get("source", "Government Mandi API"),
            "updated_at": snapshot.get("updated_at", datetime.utcnow().isoformat()),
        }

    def _parse_date(self, value: str):
        if not value:
            return None
        value = str(value).strip()
        for fmt in (
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
        ):
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
        return None

    def _safe_float(self, value):
        try:
            if isinstance(value, str):
                value = value.replace(',', '').strip()
            return float(value)
        except Exception:
            return None

    def _normalize_crop_key(self, value: str) -> str:
        if value is None:
            return ""
        return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())

    def _find_crop_in_database(self, crop_name: str) -> Optional[Dict]:
        if not crop_name or not self.price_database:
            return None

        aliases = self._get_crop_aliases(crop_name)
        alias_keys = [self._normalize_crop_key(a) for a in aliases if self._normalize_crop_key(a)]
        if not alias_keys:
            alias_keys = [self._normalize_crop_key(crop_name)]

        # 1) Exact normalized match against aliases.
        for crop in self.price_database:
            db_key = self._normalize_crop_key(crop.get("crop_name", ""))
            if db_key and db_key in alias_keys:
                return crop

        # 2) Contains match (handles spaces/hyphens and close forms).
        for crop in self.price_database:
            db_key = self._normalize_crop_key(crop.get("crop_name", ""))
            if not db_key:
                continue
            for alias_key in alias_keys:
                if alias_key and (alias_key in db_key or db_key in alias_key):
                    return crop
        return None

    def _get_crop_aliases(self, crop_name: str) -> List[str]:
        if not crop_name:
            return []
        name = str(crop_name).strip()
        lower = name.lower()
        alias_map = {
            "paddy": ["Paddy(Dhan)", "Paddy", "Rice"],
            "rice": ["Rice", "Paddy(Dhan)", "Paddy"],
            "maize": ["Maize", "Corn"],
            "corn": ["Corn", "Maize"],
            "wheat": ["Wheat"],
            "cotton": ["Cotton"],
            "groundnut": ["Groundnut", "Ground Nut", "Peanut"],
            "turmeric": ["Turmeric"],
            "chilli": ["Chilli", "Chili"],
            "onion": ["Onion"],
            "tomato": ["Tomato"],
            "banana": ["Banana"],
            "coconut": ["Coconut"],
            "sugarcane": ["Sugarcane", "Sugar Cane"],
            "millets": ["Millets", "Millet"],
        }
        aliases = alias_map.get(lower, [])
        # ensure original name first and keep unique.
        result = [name] + [a for a in aliases if a.lower() != lower]
        unique = []
        seen = set()
        for item in result:
            key = self._normalize_crop_key(item)
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        return unique
    
    def _get_fallback_broker_prices(self, crop_name: str, district: str, mandi_price: Optional[float] = None) -> Dict:
        """[DEPRECATED]"""
        return {
            "error": "Broker prices unavailable",
            "crop": crop_name,
            "district": district,
            "broker_price": None,
            "mandi_price": round(mandi_price, 2) if mandi_price else None,
            "status_code": 503
        }
    
    def _get_fallback_decision(self, crop_name: str, quantity: float) -> Dict:
        """[DEPRECATED]"""
        return {
            "error": "Market decision unavailable due to missing price data",
            "crop": crop_name,
            "status_code": 503
        }
    
    def clear_cache(self):
        """Clear market cache"""
        self.cache.clear()
        logger.info("Market cache cleared")
