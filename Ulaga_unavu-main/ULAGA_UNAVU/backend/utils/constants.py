"""
Application constants
"""

# API Response Codes
SUCCESS = 200
CREATED = 201
BAD_REQUEST = 400
UNAUTHORIZED = 401
FORBIDDEN = 403
NOT_FOUND = 404
INTERNAL_ERROR = 500

# User Roles
ROLE_USER = "user"
ROLE_ADMIN = "admin"
ROLE_EXPERT = "expert"

# Soil Properties
SOIL_TYPES = [
    "Red Soil", "Black Soil", "Alluvial Soil", "Sandy Soil",
    "Clay Soil", "Loamy Soil", "Laterite Soil", "Peaty Soil",
    "Saline Soil", "Mountain Soil"
]

SOIL_FERTILITY_LEVELS = ["Very Low", "Low", "Medium", "High", "Very High"]
SOIL_HARDNESS_LEVELS = ["Very Soft", "Soft", "Medium", "Hard", "Very Hard"]
SOIL_WATER_RETENTION = ["Very Low", "Low", "Medium", "High", "Very High"]

# Crop Seasons
SEASONS = {
    "Kharif": ["June", "July", "August", "September", "October"],
    "Rabi": ["November", "December", "January", "February", "March"],
    "Zaid": ["April", "May"]
}

# Indian States and Districts (sample)
INDIAN_STATES = [
    "Tamil Nadu", "Kerala", "Karnataka", "Andhra Pradesh", "Telangana",
    "Maharashtra", "Gujarat", "Rajasthan", "Punjab", "Haryana",
    "Uttar Pradesh", "Madhya Pradesh", "Bihar", "West Bengal", "Odisha",
    "Assam", "Jharkhand", "Chhattisgarh", "Uttarakhand", "Himachal Pradesh"
]

# Tamil Nadu Districts
TAMIL_NADU_DISTRICTS = [
    "Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem",
    "Tirunelveli", "Vellore", "Erode", "Thoothukkudi", "Dindigul",
    "Thanjavur", "Kancheepuram", "Tiruvallur", "Kanyakumari", "Karur",
    "Namakkal", "Theni", "Ramanathapuram", "Virudhunagar", "Sivaganga",
    "Pudukkottai", "Nagapattinam", "Dharmapuri", "Krishnagiri",
    "Ariyalur", "Perambalur", "Cuddalore", "Viluppuram", "Tiruvarur"
]

# Weather Conditions
WEATHER_CONDITIONS = [
    "Clear", "Cloudy", "Rain", "Heavy Rain", "Thunderstorm",
    "Fog", "Mist", "Haze", "Snow", "Windy"
]

# Disease Severity Levels
DISEASE_SEVERITY = ["Low", "Medium", "High", "Critical"]

# Market Decision Types
MARKET_DECISIONS = ["SELL", "WAIT", "HOLD", "DO NOT SELL"]

# Notification Types
NOTIFICATION_TYPES = {
    "WEATHER_ALERT": "weather",
    "FERTILIZER_REMINDER": "fertilizer",
    "DISEASE_ALERT": "disease",
    "MARKET_UPDATE": "market",
    "GROWTH_STAGE": "growth",
    "SYSTEM": "system"
}

# Color Codes for UI
COLORS = {
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "info": "#3B82F6",
    "primary": "#8B5CF6",
    "secondary": "#6B7280"
}

# Measurement Units
UNITS = {
    "temperature": {"metric": "°C", "imperial": "°F"},
    "rainfall": {"metric": "mm", "imperial": "inch"},
    "wind_speed": {"metric": "km/h", "imperial": "mph"},
    "pressure": {"metric": "hPa", "imperial": "inHg"},
    "distance": {"metric": "km", "imperial": "miles"},
    "weight": {"metric": "kg", "imperial": "lbs"},
    "area": {"metric": "hectare", "imperial": "acre"}
}

# API Rate Limits
RATE_LIMITS = {
    "public": "100/hour",
    "authenticated": "1000/hour",
    "premium": "10000/hour"
}

# File Upload Limits (in MB)
UPLOAD_LIMITS = {
    "image": 5,
    "pdf": 10,
    "video": 50
}

# Cache Timeouts (in seconds)
CACHE_TIMEOUTS = {
    "dashboard": 300,
    "weather": 900,
    "market": 1800,
    "news": 3600
}