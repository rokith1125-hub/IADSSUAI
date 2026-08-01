"""
Dataset Normalizer - Maps CNN predictions to frontend expectations
Handles label mismatches between models and datasets
"""

import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class DatasetNormalizer:
    """
    Normalizes CNN model outputs to match frontend expectations
    Handles variations in naming conventions
    """

    # Soil type mappings
    SOIL_ALIASES = {
        # CNN model outputs -> Frontend expected names
        "Alluvial_Soil": "Alluvial Soil",
        "Black_Soil": "Black Soil",
        "Cinder_Soil": "Cinder Soil",
        "Clayey_Soil": "Clay Soil",
        "Laterite_Soil": "Laterite Soil",
        "Loam_Soil": "Loam Soil",
        "Peaty_Soil": "Peaty Soil",
        "Sandy_Loam_Soil": "Sandy Loam Soil",
        "Yellow_Soil": "Yellow Soil",

        # Variations and aliases
        "alluvial soil": "Alluvial Soil",
        "black soil": "Black Soil",
        "clay soil": "Clay Soil",
        "clayey soil": "Clay Soil",
        "laterite soil": "Laterite Soil",
        "loam soil": "Loam Soil",
        "peaty soil": "Peaty Soil",
        "sandy loam soil": "Sandy Loam Soil",
        "yellow soil": "Yellow Soil",
        "sandy loam": "Sandy Loam Soil",
        "clayey": "Clay Soil",
        "alluvial": "Alluvial Soil",
        "black": "Black Soil",
        "laterite": "Laterite Soil",
        "loam": "Loam Soil",
        "peaty": "Peaty Soil",
        "yellow": "Yellow Soil",
    }

    # Disease mappings
    DISEASE_ALIASES = {
        # CNN model outputs -> Frontend expected names
        "Apple___Apple_scab": "Apple Scab",
        "Apple___Black_rot": "Apple Black Rot",
        "Apple___Cedar_apple_rust": "Apple Cedar Rust",
        "Apple___healthy": "Apple Healthy",
        "Blueberry___healthy": "Blueberry Healthy",
        "Cherry_(including_sour)___Powdery_mildew": "Cherry Powdery Mildew",
        "Cherry_(including_sour)___healthy": "Cherry Healthy",
        "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": "Corn Cercospora Leaf Spot",
        "Corn_(maize)___Common_rust_": "Corn Common Rust",
        "Corn_(maize)___Northern_Leaf_Blight": "Corn Northern Leaf Blight",
        "Corn_(maize)___healthy": "Corn Healthy",
        "Grape___Black_rot": "Grape Black Rot",
        "Grape___Esca_(Black_Measles)": "Grape Esca",
        "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "Grape Leaf Blight",
        "Grape___healthy": "Grape Healthy",
        "Orange___Haunglongbing_(Citrus_greening)": "Orange Citrus Greening",
        "Peach___Bacterial_spot": "Peach Bacterial Spot",
        "Peach___healthy": "Peach Healthy",
        "Pepper,_bell___Bacterial_spot": "Bell Pepper Bacterial Spot",
        "Pepper,_bell___healthy": "Bell Pepper Healthy",
        "Potato___Early_blight": "Potato Early Blight",
        "Potato___Late_blight": "Potato Late Blight",
        "Potato___healthy": "Potato Healthy",
        "Raspberry___healthy": "Raspberry Healthy",
        "Soybean___healthy": "Soybean Healthy",
        "Squash___Powdery_mildew": "Squash Powdery Mildew",
        "Strawberry___Leaf_scorch": "Strawberry Leaf Scorch",
        "Strawberry___healthy": "Strawberry Healthy",
        "Tomato___Bacterial_spot": "Tomato Bacterial Spot",
        "Tomato___Early_blight": "Tomato Early Blight",
        "Tomato___Late_blight": "Tomato Late Blight",
        "Tomato___Leaf_Mold": "Tomato Leaf Mold",
        "Tomato___Septoria_leaf_spot": "Tomato Septoria Leaf Spot",
        "Tomato___Spider_mites Two-spotted_spider_mite": "Tomato Spider Mites",
        "Tomato___Target_Spot": "Tomato Target Spot",
        "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "Tomato Yellow Leaf Curl Virus",
        "Tomato___Tomato_mosaic_virus": "Tomato Mosaic Virus",
        "Tomato___healthy": "Tomato Healthy",

        # Common variations
        "apple scab": "Apple Scab",
        "apple black rot": "Apple Black Rot",
        "apple cedar rust": "Apple Cedar Rust",
        "apple healthy": "Apple Healthy",
        "blueberry healthy": "Blueberry Healthy",
        "cherry powdery mildew": "Cherry Powdery Mildew",
        "cherry healthy": "Cherry Healthy",
        "corn cercospora": "Corn Cercospora Leaf Spot",
        "corn common rust": "Corn Common Rust",
        "corn northern leaf blight": "Corn Northern Leaf Blight",
        "corn healthy": "Corn Healthy",
        "grape black rot": "Grape Black Rot",
        "grape esca": "Grape Esca",
        "grape leaf blight": "Grape Leaf Blight",
        "grape healthy": "Grape Healthy",
        "orange citrus greening": "Orange Citrus Greening",
        "peach bacterial spot": "Peach Bacterial Spot",
        "peach healthy": "Peach Healthy",
        "bell pepper bacterial spot": "Bell Pepper Bacterial Spot",
        "bell pepper healthy": "Bell Pepper Healthy",
        "potato early blight": "Potato Early Blight",
        "potato late blight": "Potato Late Blight",
        "potato healthy": "Potato Healthy",
        "raspberry healthy": "Raspberry Healthy",
        "soybean healthy": "Soybean Healthy",
        "squash powdery mildew": "Squash Powdery Mildew",
        "strawberry leaf scorch": "Strawberry Leaf Scorch",
        "strawberry healthy": "Strawberry Healthy",
        "tomato bacterial spot": "Tomato Bacterial Spot",
        "tomato early blight": "Tomato Early Blight",
        "tomato late blight": "Tomato Late Blight",
        "tomato leaf mold": "Tomato Leaf Mold",
        "tomato septoria": "Tomato Septoria Leaf Spot",
        "tomato spider mites": "Tomato Spider Mites",
        "tomato target spot": "Tomato Target Spot",
        "tomato yellow leaf curl": "Tomato Yellow Leaf Curl Virus",
        "tomato mosaic": "Tomato Mosaic Virus",
        "tomato healthy": "Tomato Healthy",
    }

    @staticmethod
    def normalize_soil_name(soil_name: str) -> str:
        """
        Normalize soil name from CNN prediction to frontend format

        Args:
            soil_name: Raw CNN prediction

        Returns:
            Normalized soil name
        """
        if not soil_name:
            return "Unknown Soil"

        # Clean and normalize
        clean_name = str(soil_name).strip().lower()

        # Check direct mapping
        if clean_name in DatasetNormalizer.SOIL_ALIASES:
            return DatasetNormalizer.SOIL_ALIASES[clean_name]

        # Try partial matches
        for key, value in DatasetNormalizer.SOIL_ALIASES.items():
            if key.lower() in clean_name or clean_name in key.lower():
                return value

        # Fallback - capitalize and clean
        logger.warning(f"Unmapped soil name: {soil_name}")
        return soil_name.replace('_', ' ').title()

    @staticmethod
    def normalize_disease_name(disease_name: str) -> str:
        """
        Normalize disease name from CNN prediction to frontend format

        Args:
            disease_name: Raw CNN prediction

        Returns:
            Normalized disease name
        """
        if not disease_name:
            return "Unknown Disease"

        # Clean and normalize
        clean_name = str(disease_name).strip()

        # Check direct mapping
        if clean_name in DatasetNormalizer.DISEASE_ALIASES:
            return DatasetNormalizer.DISEASE_ALIASES[clean_name]

        # Try partial matches
        for key, value in DatasetNormalizer.DISEASE_ALIASES.items():
            if key.lower() in clean_name.lower() or clean_name.lower() in key.lower():
                return value

        # Fallback - clean up underscores and title case
        logger.warning(f"Unmapped disease name: {disease_name}")
        return disease_name.replace('___', ' ').replace('_', ' ').title()

    @staticmethod
    def get_soil_properties(soil_name: str) -> Dict[str, Any]:
        """
        Get soil properties based on normalized name

        Args:
            soil_name: Normalized soil name

        Returns:
            Soil properties dictionary
        """
        soil_properties = {
            "Alluvial Soil": {
                "fertility": "High",
                "drainage": "Good",
                "ph_level": "Neutral",
                "texture": "Loamy",
                "water_retention": "Medium",
                "benefits": ["High fertility", "Good drainage", "Suitable for most crops"]
            },
            "Black Soil": {
                "fertility": "Very High",
                "drainage": "Poor",
                "ph_level": "Neutral to Slightly Alkaline",
                "texture": "Clayey",
                "water_retention": "High",
                "benefits": ["Very fertile", "High water retention", "Good for cotton and sugarcane"]
            },
            "Clay Soil": {
                "fertility": "Medium",
                "drainage": "Poor",
                "ph_level": "Neutral",
                "texture": "Clayey",
                "water_retention": "Very High",
                "benefits": ["High water retention", "Rich in minerals", "Good for rice and wheat"]
            },
            "Laterite Soil": {
                "fertility": "Low",
                "drainage": "Good",
                "ph_level": "Acidic",
                "texture": "Sandy",
                "water_retention": "Low",
                "benefits": ["Good drainage", "Suitable for tea and coffee", "Iron-rich"]
            },
            "Loam Soil": {
                "fertility": "High",
                "drainage": "Excellent",
                "ph_level": "Neutral",
                "texture": "Loamy",
                "water_retention": "Medium",
                "benefits": ["Balanced properties", "Good for most vegetables", "Easy to work"]
            },
            "Peaty Soil": {
                "fertility": "High",
                "drainage": "Poor",
                "ph_level": "Acidic",
                "texture": "Organic",
                "water_retention": "Very High",
                "benefits": ["High organic matter", "Good for potatoes", "Rich in nutrients"]
            },
            "Sandy Loam Soil": {
                "fertility": "Medium",
                "drainage": "Good",
                "ph_level": "Neutral",
                "texture": "Sandy Loam",
                "water_retention": "Low",
                "benefits": ["Good drainage", "Easy to work", "Suitable for carrots and potatoes"]
            },
            "Yellow Soil": {
                "fertility": "Medium",
                "drainage": "Good",
                "ph_level": "Slightly Acidic",
                "texture": "Sandy",
                "water_retention": "Low",
                "benefits": ["Good drainage", "Suitable for citrus", "Iron-rich"]
            }
        }

        return soil_properties.get(soil_name, {
            "fertility": "Unknown",
            "drainage": "Unknown",
            "ph_level": "Unknown",
            "texture": "Unknown",
            "water_retention": "Unknown",
            "benefits": ["Properties need to be analyzed"]
        })

    @staticmethod
    def get_disease_severity(disease_name: str) -> str:
        """
        Get disease severity level

        Args:
            disease_name: Normalized disease name

        Returns:
            Severity level (Low/Medium/High)
        """
        # Healthy crops
        if "healthy" in disease_name.lower():
            return "None"

        # High severity diseases
        high_severity = [
            "late blight", "black rot", "citrus greening", "yellow leaf curl",
            "mosaic virus", "northern leaf blight", "esca"
        ]

        # Medium severity diseases
        medium_severity = [
            "early blight", "bacterial spot", "powdery mildew", "leaf mold",
            "septoria leaf spot", "target spot", "spider mites", "leaf scorch",
            "common rust", "cercospora", "apple scab", "cedar rust"
        ]

        disease_lower = disease_name.lower()

        for disease in high_severity:
            if disease in disease_lower:
                return "High"

        for disease in medium_severity:
            if disease in disease_lower:
                return "Medium"

        return "Low"

    @staticmethod
    def get_disease_treatment(disease_name: str) -> Dict[str, Any]:
        """
        Get treatment recommendations for disease

        Args:
            disease_name: Normalized disease name

        Returns:
            Treatment information
        """
        treatments = {
            "Tomato Late Blight": {
                "organic": ["Copper fungicide spray", "Remove infected leaves", "Improve air circulation"],
                "chemical": ["Chlorothalonil", "Mancozeb"],
                "preventive": ["Avoid overhead watering", "Space plants properly", "Crop rotation"]
            },
            "Tomato Early Blight": {
                "organic": ["Neem oil spray", "Baking soda solution", "Compost tea"],
                "chemical": ["Chlorothalonil", "Copper fungicide"],
                "preventive": ["Mulching", "Proper spacing", "Avoid wet foliage"]
            },
            "Tomato Bacterial Spot": {
                "organic": ["Copper fungicide", "Remove infected plants"],
                "chemical": ["Streptomycin", "Copper hydroxide"],
                "preventive": ["Disease-free seeds", "Avoid overhead watering", "Crop rotation"]
            },
            "Potato Late Blight": {
                "organic": ["Copper fungicide", "Remove infected plants immediately"],
                "chemical": ["Mancozeb", "Chlorothalonil"],
                "preventive": ["Plant resistant varieties", "Avoid wet conditions"]
            },
            "Apple Scab": {
                "organic": ["Neem oil", "Baking soda spray"],
                "chemical": ["Captan", "Myclobutanil"],
                "preventive": ["Rake fallen leaves", "Prune properly", "Resistant varieties"]
            }
        }

        return treatments.get(disease_name, {
            "organic": ["Consult local agricultural extension"],
            "chemical": ["Consult agricultural expert"],
            "preventive": ["Proper plant spacing", "Good air circulation", "Regular monitoring"]
        })


# Factory function
def get_normalizer():
    """Get dataset normalizer instance"""
    return DatasetNormalizer()
