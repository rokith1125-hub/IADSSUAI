"""
Image Service for ULAGA_UNAVU - FREE APIs Only
Provides crop, soil, disease images using:
1. Pre-defined URLs (Instant, Free)
2. Pollinations.ai (FREE - AI Image Generation)
3. Unsplash API (Free - 50 req/hour)
4. Pexels API (Free - 200 req/hour)
5. Pixabay API (Free - 100 req/min)
"""

import os
import time
import logging
import requests
from typing import Optional, Dict, List, Any
from urllib.parse import quote

logger = logging.getLogger(__name__)


class SmartImageEngine:
    """Service for fetching crop/agriculture images - 100% FREE APIs"""
    
    # ============================================================
    # PRE-DEFINED CROP IMAGES (Unsplash - Free to use)
    # ============================================================
    CROP_IMAGES = {
        # Cereals
        "rice": "https://images.unsplash.com/photo-1536304993881-ff6e9eefa2a6?w=600",
        "paddy": "https://images.unsplash.com/photo-1536304993881-ff6e9eefa2a6?w=600",
        "wheat": "https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?w=600",
        "maize": "https://images.unsplash.com/photo-1551754655-cd27e38d2076?w=600",
        "corn": "https://images.unsplash.com/photo-1551754655-cd27e38d2076?w=600",
        "bajra": "https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=600",
        "jowar": "https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=600",
        "ragi": "https://images.unsplash.com/photo-1625246333195-78d9c38ad449?w=600",
        
        # Cash Crops
        "cotton": "https://images.unsplash.com/photo-1594897030264-ab7d87efc473?w=600",
        "sugarcane": "https://images.unsplash.com/photo-1527847263472-aa5338d178b8?w=600",
        "jute": "https://images.unsplash.com/photo-1590682680695-43b964a3ae17?w=600",
        "tobacco": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        
        # Pulses
        "groundnut": "https://images.unsplash.com/photo-1567892737950-30c4db37cd89?w=600",
        "soybean": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600",
        "chickpea": "https://images.unsplash.com/photo-1515543904067-fd1241eb5cb9?w=600",
        "lentil": "https://images.unsplash.com/photo-1515543904067-fd1241eb5cb9?w=600",
        "moong": "https://images.unsplash.com/photo-1515543904067-fd1241eb5cb9?w=600",
        "urad": "https://images.unsplash.com/photo-1515543904067-fd1241eb5cb9?w=600",
        "toor": "https://images.unsplash.com/photo-1515543904067-fd1241eb5cb9?w=600",
        
        # Vegetables
        "tomato": "https://images.unsplash.com/photo-1546470427-227c7369a9b9?w=600",
        "potato": "https://images.unsplash.com/photo-1518977676601-b53f82abb29?w=600",
        "onion": "https://images.unsplash.com/photo-1618512496248-a07f6f3ace5e?w=600",
        "brinjal": "https://images.unsplash.com/photo-1615484477778-ca3b77940c25?w=600",
        "eggplant": "https://images.unsplash.com/photo-1615484477778-ca3b77940c25?w=600",
        "cabbage": "https://images.unsplash.com/photo-1594282486552-05b4d80fbb9f?w=600",
        "carrot": "https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?w=600",
        "beans": "https://images.unsplash.com/photo-1567375698348-5d9d5ae5f2de?w=600",
        "cauliflower": "https://images.unsplash.com/photo-1568584711075-3d021a7c3ca3?w=600",
        "spinach": "https://images.unsplash.com/photo-1576045057995-568f588f82fb?w=600",
        "chilli": "https://images.unsplash.com/photo-1588252303782-cb80119abd6d?w=600",
        "capsicum": "https://images.unsplash.com/photo-1563565375-f3fdfdb60d65?w=600",
        "okra": "https://images.unsplash.com/photo-1425543103986-22abb7d7e8d2?w=600",
        "ladyfinger": "https://images.unsplash.com/photo-1425543103986-22abb7d7e8d2?w=600",
        "cucumber": "https://images.unsplash.com/photo-1449300079323-02e209d9d3a6?w=600",
        "pumpkin": "https://images.unsplash.com/photo-1570586437263-ab629fccc818?w=600",
        "bitter_gourd": "https://images.unsplash.com/photo-1594995846645-e58528c11518?w=600",
        "bottle_gourd": "https://images.unsplash.com/photo-1594995846645-e58528c11518?w=600",
        "drumstick": "https://images.unsplash.com/photo-1567375698348-5d9d5ae5f2de?w=600",
        
        # Fruits
        "banana": "https://images.unsplash.com/photo-1603833665858-e61d17a86224?w=600",
        "mango": "https://images.unsplash.com/photo-1553279768-865429fa0078?w=600",
        "coconut": "https://images.unsplash.com/photo-1580984969071-a8da5656c2fb?w=600",
        "papaya": "https://images.unsplash.com/photo-1517282009859-f000ec3b26fe?w=600",
        "guava": "https://images.unsplash.com/photo-1536511132770-e5058c7e8c46?w=600",
        "pomegranate": "https://images.unsplash.com/photo-1541344999736-4a22e0c45508?w=600",
        "grapes": "https://images.unsplash.com/photo-1537640538966-79f369143f8f?w=600",
        "orange": "https://images.unsplash.com/photo-1547514701-42782101795e?w=600",
        "lemon": "https://images.unsplash.com/photo-1590502593747-42a996133562?w=600",
        "apple": "https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=600",
        "watermelon": "https://images.unsplash.com/photo-1563114773-84221bd62daa?w=600",
        "pineapple": "https://images.unsplash.com/photo-1550258987-190a2d41a8ba?w=600",
        
        # Spices
        "turmeric": "https://images.unsplash.com/photo-1615485500704-8e990f9900f7?w=600",
        "ginger": "https://images.unsplash.com/photo-1615485500834-bc10199bc727?w=600",
        "garlic": "https://images.unsplash.com/photo-1540148426945-6cf22a6b2383?w=600",
        "coriander": "https://images.unsplash.com/photo-1592861956120-e524fc739696?w=600",
        "cumin": "https://images.unsplash.com/photo-1599909533681-74a36a51ef54?w=600",
        "cardamom": "https://images.unsplash.com/photo-1596547609652-9cf5d8e76921?w=600",
        "pepper": "https://images.unsplash.com/photo-1599909533681-74a36a51ef54?w=600",
        
        # Oil Seeds
        "mustard": "https://images.unsplash.com/photo-1563514227147-6d2ff665a6a0?w=600",
        "sunflower": "https://images.unsplash.com/photo-1597848212624-a19eb35e2651?w=600",
        "sesame": "https://images.unsplash.com/photo-1515543904067-fd1241eb5cb9?w=600",
        "castor": "https://images.unsplash.com/photo-1515543904067-fd1241eb5cb9?w=600",
        
        # Default
        "default": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=600",
        "agriculture": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=600",
        "farm": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=600"
    }
    
    # ============================================================
    # SOIL TYPE IMAGES
    # ============================================================
    SOIL_IMAGES = {
        "alluvial": "https://images.unsplash.com/photo-1509587584298-0f3b3a3a1797?w=600",
        "black": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=600",
        "black_soil": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=600",
        "red": "https://images.unsplash.com/photo-1585336261022-680e295ce3fe?w=600",
        "red_soil": "https://images.unsplash.com/photo-1585336261022-680e295ce3fe?w=600",
        "laterite": "https://images.unsplash.com/photo-1585336261022-680e295ce3fe?w=600",
        "clay": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=600",
        "clayey": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=600",
        "sandy": "https://images.unsplash.com/photo-1509587584298-0f3b3a3a1797?w=600",
        "loamy": "https://images.unsplash.com/photo-1509587584298-0f3b3a3a1797?w=600",
        "loam": "https://images.unsplash.com/photo-1509587584298-0f3b3a3a1797?w=600",
        "desert": "https://images.unsplash.com/photo-1509316785289-025f5b846b35?w=600",
        "mountain": "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=600",
        "forest": "https://images.unsplash.com/photo-1448375240586-882707db888b?w=600",
        "saline": "https://images.unsplash.com/photo-1509587584298-0f3b3a3a1797?w=600",
        "peaty": "https://images.unsplash.com/photo-1560493676-04071c5f467b?w=600",
        "default": "https://images.unsplash.com/photo-1509587584298-0f3b3a3a1797?w=600"
    }
    
    # ============================================================
    # DISEASE IMAGES
    # ============================================================
    DISEASE_IMAGES = {
        "leaf_blight": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        "blight": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        "root_rot": "https://images.unsplash.com/photo-1591857177580-dc82b9ac4e1e?w=600",
        "rot": "https://images.unsplash.com/photo-1591857177580-dc82b9ac4e1e?w=600",
        "powdery_mildew": "https://images.unsplash.com/photo-1589923188651-268a9765e432?w=600",
        "mildew": "https://images.unsplash.com/photo-1589923188651-268a9765e432?w=600",
        "bacterial_wilt": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        "wilt": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        "rust": "https://images.unsplash.com/photo-1589923188651-268a9765e432?w=600",
        "blast": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        "mosaic": "https://images.unsplash.com/photo-1589923188651-268a9765e432?w=600",
        "virus": "https://images.unsplash.com/photo-1589923188651-268a9765e432?w=600",
        "fungal": "https://images.unsplash.com/photo-1589923188651-268a9765e432?w=600",
        "bacterial": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        "pest": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?w=600",
        "insect": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?w=600",
        "aphid": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?w=600",
        "caterpillar": "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62?w=600",
        "healthy": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600",
        "default": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600"
    }
    
    def __init__(self):
        """Initialize SmartImageEngine with failover, key rotation, and cache."""
        self.pollinations_base_url = os.getenv(
            "POLLINATIONS_API_URL",
            "https://image.pollinations.ai/prompt",
        ).rstrip("/")
        self.provider_priority = self._load_provider_priority()
        self.provider_cooldown_seconds = self._read_int_env("IMAGE_PROVIDER_COOLDOWN_SECONDS", 300)
        self.key_cooldown_seconds = self._read_int_env("IMAGE_KEY_COOLDOWN_SECONDS", 300)
        self.cache_ttl_seconds = self._read_int_env("IMAGE_CACHE_TTL_SECONDS", 6 * 60 * 60)

        self.provider_cooldowns: Dict[str, float] = {}
        self.key_cooldowns: Dict[str, Dict[str, float]] = {
            "unsplash": {},
            "pexels": {},
            "pixabay": {},
        }
        self.key_indices: Dict[str, int] = {
            "unsplash": 0,
            "pexels": 0,
            "pixabay": 0,
        }
        self.keys: Dict[str, List[str]] = {
            "unsplash": self._load_api_keys(
                keys_env="UNSPLASH_KEYS",
                single_envs=["UNSPLASH_ACCESS_KEY", "UNSPLASH_ACCESS_KEy"],
            ),
            "pexels": self._load_api_keys(
                keys_env="PEXELS_KEYS",
                single_envs=["PEXELS_API_KEY"],
            ),
            "pixabay": self._load_api_keys(
                keys_env="PIXABAY_KEYS",
                single_envs=["PIXABAY_API_KEY"],
            ),
        }
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.providers = {
            "pollinations": self._provider_pollinations,
            "unsplash": self._provider_unsplash,
            "pexels": self._provider_pexels,
            "pixabay": self._provider_pixabay,
        }

        logger.info(
            "SmartImageEngine initialized with provider_priority=%s",
            ",".join(self.provider_priority),
        )

    # ============================================================
    # MAIN METHODS
    # ============================================================

    def get_crop_image(self, crop_name: str) -> Dict[str, Any]:
        """Fetch crop image with provider failover and cache."""
        crop_key = self._normalize_name(crop_name)
        cache_key = f"crop::{crop_key}"

        cached = self._check_cache(cache_key)
        if cached:
            return self._build_success(
                image_url=cached["image_url"],
                thumbnail_url=cached["thumbnail_url"],
                source=cached["source"],
                provider=cached["provider"],
                cached=True,
                fallback_used=False,
                provider_priority=self.provider_priority,
            )

        result = self._get_image_from_priority(crop_name=crop_name, stage=None)
        if result.get("success"):
            self._set_cache(cache_key, result["data"])
            return result

        predefined_url = self.CROP_IMAGES.get(crop_key)
        if predefined_url and crop_key not in {"default", "agriculture", "farm"}:
            logger.warning(
                "All providers failed. Using predefined crop image for '%s'.",
                crop_name,
            )
            if self._is_valid_image_url(predefined_url):
                fallback_data = {
                    "image_url": predefined_url,
                    "thumbnail_url": self._thumbnail_from_url(predefined_url),
                    "source": "stock",
                    "provider": "predefined",
                }
                self._set_cache(cache_key, fallback_data)
                return self._build_success(
                    image_url=fallback_data["image_url"],
                    thumbnail_url=fallback_data["thumbnail_url"],
                    source=fallback_data["source"],
                    provider=fallback_data["provider"],
                    cached=False,
                    fallback_used=True,
                    provider_priority=self.provider_priority,
                )

            logger.error(
                "Predefined image URL failed validation for crop '%s': %s",
                crop_name,
                predefined_url,
            )

        return result

    def get_crop_lifecycle_image(self, crop_name: str, stage: str) -> Dict[str, Any]:
        """Fetch lifecycle stage image for crop."""
        stage_map = {
            "seed": "seed",
            "seedling": "seedling",
            "vegetative": "vegetative",
            "flowering": "flowering",
            "harvest": "harvest",
            "market_ready": "market_ready",
            "fruiting": "flowering",
        }
        normalized_stage = stage_map.get(self._normalize_name(stage), None)
        if not normalized_stage:
            return self._build_error("Invalid lifecycle stage")

        crop_key = self._normalize_name(crop_name)
        cache_key = f"crop_lifecycle::{crop_key}::{normalized_stage}"
        cached = self._check_cache(cache_key)
        if cached:
            return self._build_success(
                image_url=cached["image_url"],
                thumbnail_url=cached["thumbnail_url"],
                source=cached["source"],
                provider=cached["provider"],
                cached=True,
                fallback_used=False,
                provider_priority=self.provider_priority,
            )

        result = self._get_image_from_priority(crop_name=crop_name, stage=normalized_stage)
        if result.get("success"):
            self._set_cache(cache_key, result["data"])
            return result

        predefined_url = self.CROP_IMAGES.get(crop_key)
        if predefined_url and crop_key not in {"default", "agriculture", "farm"}:
            logger.warning(
                "Lifecycle image provider failed for crop='%s', stage='%s'. "
                "Using predefined stock image.",
                crop_name,
                normalized_stage,
            )
            if self._is_valid_image_url(predefined_url):
                fallback_data = {
                    "image_url": predefined_url,
                    "thumbnail_url": self._thumbnail_from_url(predefined_url),
                    "source": "stock",
                    "provider": "predefined",
                }
                self._set_cache(cache_key, fallback_data)
                return self._build_success(
                    image_url=fallback_data["image_url"],
                    thumbnail_url=fallback_data["thumbnail_url"],
                    source=fallback_data["source"],
                    provider=fallback_data["provider"],
                    cached=False,
                    fallback_used=True,
                    provider_priority=self.provider_priority,
                )

        return result

    def get_crop_growth_stage_image(self, crop_name: str, growth_stage: str) -> Dict[str, Any]:
        """Backward-compatible growth-stage image method."""
        return self.get_crop_lifecycle_image(crop_name=crop_name, stage=growth_stage)

    def generate_pollinations_image(self, crop_name: str, style: str = "photorealistic") -> Dict[str, Any]:
        """
        Generate AI image from Pollinations first, then fallback to stock providers.
        """
        prompts = {
            "photorealistic": (
                f"A high quality photo of {crop_name} crop in an Indian farm field, natural light"
            ),
            "artistic": (
                f"An artistic painting style image of {crop_name} crop in agriculture"
            ),
            "illustration": (
                f"A botanical illustration of {crop_name} crop with clear leaves and stem"
            ),
        }
        prompt_override = prompts.get(style, prompts["photorealistic"])
        pollinations_result = self._provider_pollinations(
            crop_name=crop_name,
            stage=None,
            prompt_override=prompt_override,
        )
        if pollinations_result.get("success"):
            image_url = pollinations_result["image_url"]
            if self._is_valid_image_url(image_url):
                return self._build_success(
                    image_url=image_url,
                    thumbnail_url=pollinations_result.get("thumbnail_url"),
                    source="ai_generated",
                    provider="pollinations",
                    cached=False,
                    fallback_used=False,
                    provider_priority=self.provider_priority,
                )

        logger.warning("Pollinations failed for crop='%s', switching to stock providers.", crop_name)
        self._mark_provider_unhealthy("pollinations", "pollinations_generation_failed")
        stock_priority = [p for p in self.provider_priority if p != "pollinations"]
        result = self._get_image_from_priority(
            crop_name=crop_name,
            stage=None,
            provider_priority=stock_priority,
        )
        if result.get("success"):
            result["meta"]["fallback_used"] = True
        return result

    def get_ai_generated_crop_image(self, crop_name: str) -> Dict[str, Any]:
        """Backward-compatible AI image method."""
        return self.generate_pollinations_image(crop_name, style="photorealistic")

    def get_soil_image(self, soil_type: str) -> Dict[str, Any]:
        """Get soil image from predefined stock set."""
        soil_key = self._normalize_name(soil_type)
        image_url = self.SOIL_IMAGES.get(soil_key)
        fallback_used = False
        if not image_url:
            image_url = self.SOIL_IMAGES.get("default")
            fallback_used = True
            logger.warning("Unknown soil type '%s'. Falling back to default soil image.", soil_type)

        if not image_url or not self._is_valid_image_url(image_url):
            logger.error("Soil image unavailable for soil type '%s'.", soil_type)
            return self._build_error("All image providers unavailable", retry_after=self.provider_cooldown_seconds)

        return self._build_success(
            image_url=image_url,
            thumbnail_url=self._thumbnail_from_url(image_url),
            source="stock",
            provider="predefined",
            cached=False,
            fallback_used=fallback_used,
            provider_priority=self.provider_priority,
        )

    def get_disease_image(self, disease_name: str) -> Dict[str, Any]:
        """Get disease image from predefined stock set."""
        disease_key = self._normalize_name(disease_name)
        image_url = self.DISEASE_IMAGES.get(disease_key)
        fallback_used = False

        if not image_url:
            for key, candidate in self.DISEASE_IMAGES.items():
                if key in disease_key or disease_key in key:
                    image_url = candidate
                    fallback_used = True
                    break

        if not image_url:
            image_url = self.DISEASE_IMAGES.get("default")
            fallback_used = True
            logger.warning(
                "Unknown disease type '%s'. Falling back to default disease image.",
                disease_name,
            )

        if not image_url or not self._is_valid_image_url(image_url):
            logger.error("Disease image unavailable for disease '%s'.", disease_name)
            return self._build_error("All image providers unavailable", retry_after=self.provider_cooldown_seconds)

        return self._build_success(
            image_url=image_url,
            thumbnail_url=self._thumbnail_from_url(image_url),
            source="stock",
            provider="predefined",
            cached=False,
            fallback_used=fallback_used,
            provider_priority=self.provider_priority,
        )

    def get_multiple_crop_images(self, crop_names: List[str]) -> List[Dict[str, Any]]:
        """Get crop images for multiple crop names."""
        return [self.get_crop_image(crop) for crop in crop_names]

    def save_image(self, image_data: Any, filename: str = "", folder: str = "uploads"):
        """
        Save image bytes/file-like payload to disk.

        Returns:
            tuple: (filename, filepath)
        """
        try:
            payload = b""
            resolved_filename = filename or ""

            if isinstance(image_data, (bytes, bytearray)):
                payload = bytes(image_data)
            elif hasattr(image_data, "read"):
                if not resolved_filename:
                    resolved_filename = getattr(image_data, "filename", "")
                payload = image_data.read()
            elif hasattr(image_data, "file") and hasattr(image_data.file, "read"):
                if not resolved_filename:
                    resolved_filename = getattr(image_data, "filename", "")
                payload = image_data.file.read()
            else:
                raise ValueError("Unsupported image input type")

            if not payload:
                raise ValueError("Empty image payload")

            os.makedirs(folder, exist_ok=True)

            import uuid

            ext = os.path.splitext(resolved_filename)[1].lower() if resolved_filename else ".jpg"
            if not ext:
                ext = ".jpg"

            unique_filename = f"{uuid.uuid4().hex}{ext}"
            filepath = os.path.join(folder, unique_filename)

            with open(filepath, "wb") as out_file:
                out_file.write(payload)

            logger.info("Image saved: %s", filepath)
            return unique_filename, filepath

        except Exception as e:
            logger.error("Failed to save image: %s", e)
            raise

    # ============================================================
    # INTERNAL HELPERS
    # ============================================================

    def _read_int_env(self, key: str, default: int) -> int:
        value = os.getenv(key, "").strip()
        if not value:
            return default
        try:
            return max(1, int(value))
        except Exception:
            return default

    def _normalize_name(self, name: str) -> str:
        if not name:
            return "default"
        return str(name).strip().lower().replace(" ", "_").replace("-", "_")

    def _load_provider_priority(self) -> List[str]:
        default_priority = ["pollinations", "unsplash", "pexels", "pixabay"]
        configured = os.getenv(
            "IMAGE_PROVIDER_PRIORITY",
            "pollinations,unsplash,pexels,pixabay",
        )
        requested = [p.strip().lower() for p in configured.split(",") if p.strip()]
        priority: List[str] = []
        for provider in requested:
            if provider in default_priority and provider not in priority:
                priority.append(provider)
        for provider in default_priority:
            if provider not in priority:
                priority.append(provider)
        return priority

    def _load_api_keys(self, keys_env: str, single_envs: List[str]) -> List[str]:
        keys: List[str] = []
        raw = os.getenv(keys_env, "")
        if raw:
            keys.extend([k.strip() for k in raw.split(",") if k.strip()])

        for env_name in single_envs:
            single_key = os.getenv(env_name, "").strip()
            if single_key:
                keys.append(single_key)

        # De-duplicate preserving order
        seen = set()
        unique_keys = []
        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            unique_keys.append(key)
        return unique_keys

    def _provider_is_healthy(self, provider: str) -> bool:
        now = time.time()
        cooldown_until = self.provider_cooldowns.get(provider)
        if not cooldown_until:
            return True
        if now >= cooldown_until:
            self.provider_cooldowns.pop(provider, None)
            return True
        return False

    def _mark_provider_unhealthy(self, provider: str, reason: str) -> None:
        self.provider_cooldowns[provider] = time.time() + self.provider_cooldown_seconds
        logger.error(
            "Provider '%s' marked unhealthy for %ss. Reason: %s",
            provider,
            self.provider_cooldown_seconds,
            reason,
        )

    def _key_on_cooldown(self, provider: str, key: str) -> bool:
        now = time.time()
        cooldown_until = self.key_cooldowns.get(provider, {}).get(key)
        if not cooldown_until:
            return False
        if now >= cooldown_until:
            self.key_cooldowns.get(provider, {}).pop(key, None)
            return False
        return True

    def _next_api_key(self, provider: str) -> Optional[str]:
        keys = self.keys.get(provider, [])
        if not keys:
            return None

        start = self.key_indices.get(provider, 0) % len(keys)
        for idx in range(len(keys)):
            key = keys[(start + idx) % len(keys)]
            if self._key_on_cooldown(provider, key):
                continue
            self.key_indices[provider] = (start + idx + 1) % len(keys)
            return key
        return None

    def _mark_key_failed(self, provider: str, api_key: str) -> None:
        self.key_cooldowns.setdefault(provider, {})[api_key] = (
            time.time() + self.key_cooldown_seconds
        )
        logger.warning(
            "Provider key on cooldown: provider=%s cooldown=%ss",
            provider,
            self.key_cooldown_seconds,
        )

    def _check_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cached = self.cache.get(cache_key)
        if not cached:
            return None

        cached_at = cached.get("timestamp", 0)
        if time.time() - cached_at > self.cache_ttl_seconds:
            self.cache.pop(cache_key, None)
            return None
        return cached

    def _set_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        self.cache[cache_key] = {
            "image_url": data.get("image_url"),
            "thumbnail_url": data.get("thumbnail_url") or data.get("image_url"),
            "source": data.get("source", "stock"),
            "provider": data.get("provider", "unknown"),
            "timestamp": time.time(),
        }

    def _build_success(
        self,
        image_url: str,
        thumbnail_url: Optional[str],
        source: str,
        provider: str,
        cached: bool,
        fallback_used: bool,
        provider_priority: List[str],
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "image_url": image_url,
                "thumbnail_url": thumbnail_url or image_url,
                "source": source,
                "provider": provider,
                "cached": bool(cached),
            },
            "meta": {
                "provider_priority": provider_priority,
                "fallback_used": bool(fallback_used),
            },
        }

    def _build_error(self, message: str, retry_after: Optional[int] = None) -> Dict[str, Any]:
        payload = {
            "success": False,
            "error": message,
        }
        if retry_after is not None:
            payload["retry_after"] = retry_after
        return payload

    def _thumbnail_from_url(self, image_url: str) -> str:
        if not image_url:
            return ""
        if "w=600" in image_url:
            return image_url.replace("w=600", "w=200")
        return image_url

    def _is_valid_image_url(self, image_url: str) -> bool:
        """Validate image URL without aggressive blocking."""
        if not image_url or not isinstance(image_url, str):
            return False
        if not image_url.startswith("http"):
            return False
            
        # Pollinations URLs are generated on the fly - don't hit them with a request here
        if "pollinations.ai" in image_url:
            return True
            
        try:
            # Short timeout for validation - better to occasionally show a broken image 
            # than to block the whole recommendation API for 6 seconds.
            head = requests.head(image_url, allow_redirects=True, timeout=2)
            if head.status_code < 400:
                return True
            # Some platforms block HEAD
            if head.status_code in (403, 405):
                return True # Optimistic for these specific status codes
            return False
        except Exception:
            # If we can't even reach the domain, it's probably invalid
            return False

    def _build_crop_queries(self, crop_name: str, stage: Optional[str] = None) -> List[str]:
        crop = str(crop_name).strip()
        if not stage:
            return [
                f"{crop} crop agriculture india",
                f"{crop} farming field",
                f"{crop} plant cultivation",
            ]

        stage_text = stage.replace("_", " ")
        return [
            f"{crop} {stage_text} stage agriculture",
            f"{crop} {stage_text} crop field india",
            f"{crop} farming lifecycle {stage_text}",
        ]

    def _get_image_from_priority(
        self,
        crop_name: str,
        stage: Optional[str],
        provider_priority: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        order = provider_priority or self.provider_priority
        fallback_used = False

        for idx, provider in enumerate(order):
            provider_fn = self.providers.get(provider)
            if not provider_fn:
                continue

            if not self._provider_is_healthy(provider):
                logger.warning("Skipping provider '%s' due to active cooldown", provider)
                fallback_used = True
                continue

            try:
                response = provider_fn(crop_name=crop_name, stage=stage)
            except Exception as exc:
                response = {
                    "success": False,
                    "error": str(exc),
                    "status_code": 500,
                }

            if response.get("success"):
                image_url = response.get("image_url")
                if not self._is_valid_image_url(image_url):
                    logger.error("Provider '%s' returned invalid URL: %s", provider, image_url)
                    self._mark_provider_unhealthy(provider, "invalid_url")
                    fallback_used = True
                    continue

                logger.info("Image provider success: provider=%s crop=%s", provider, crop_name)
                return self._build_success(
                    image_url=image_url,
                    thumbnail_url=response.get("thumbnail_url"),
                    source=response.get("source", "stock"),
                    provider=provider,
                    cached=False,
                    fallback_used=fallback_used or idx > 0,
                    provider_priority=order,
                )

            api_key = response.get("api_key")
            status_code = response.get("status_code")
            error_reason = response.get("error", "provider_error")

            if status_code == 403 and api_key:
                self._mark_key_failed(provider, api_key)

            self._mark_provider_unhealthy(provider, error_reason)
            fallback_used = True

        return self._build_error(
            "All image providers unavailable",
            retry_after=self.provider_cooldown_seconds,
        )

    def _provider_pollinations(
        self,
        crop_name: str,
        stage: Optional[str],
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        stage_prompt = {
            "seed": "seeds ready for sowing",
            "seedling": "young seedlings emerging from soil",
            "vegetative": "healthy vegetative growth with green leaves",
            "flowering": "flowers blooming in crop field",
            "harvest": "mature crop ready for harvest",
            "market_ready": "freshly harvested crop ready for market",
        }
        lifecycle_text = stage_prompt.get(stage or "", "healthy crop growing in a farm")
        prompt = prompt_override or (
            f"Realistic photo of {crop_name} crop, {lifecycle_text}, indian agriculture, natural light"
        )
        encoded_prompt = quote(prompt)
        image_url = f"{self.pollinations_base_url}/{encoded_prompt}?width=900&height=600&nologo=true"
        thumbnail_url = f"{self.pollinations_base_url}/{encoded_prompt}?width=300&height=200&nologo=true"

        return {
            "success": True,
            "image_url": image_url,
            "thumbnail_url": thumbnail_url,
            "source": "ai_generated",
            "provider": "pollinations",
        }

    def _provider_unsplash(self, crop_name: str, stage: Optional[str]) -> Dict[str, Any]:
        api_key = self._next_api_key("unsplash")
        if not api_key:
            return {
                "success": False,
                "error": "Unsplash key unavailable",
                "status_code": 503,
            }

        last_status = 500
        for query in self._build_crop_queries(crop_name, stage):
            try:
                response = requests.get(
                    "https://api.unsplash.com/search/photos",
                    params={
                        "query": query,
                        "per_page": 1,
                        "orientation": "landscape",
                    },
                    headers={"Authorization": f"Client-ID {api_key}"},
                    timeout=8,
                )
                last_status = response.status_code
                if response.status_code == 403:
                    return {
                        "success": False,
                        "error": "Unsplash access forbidden",
                        "status_code": 403,
                        "api_key": api_key,
                    }
                if response.status_code != 200:
                    continue

                payload = response.json() or {}
                results = payload.get("results") or []
                if not results:
                    continue
                photo = results[0]
                urls = photo.get("urls", {})
                image_url = urls.get("regular")
                thumb = urls.get("thumb") or urls.get("small")
                if image_url:
                    return {
                        "success": True,
                        "image_url": image_url,
                        "thumbnail_url": thumb or image_url,
                        "source": "stock",
                        "provider": "unsplash",
                    }
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"Unsplash request failed: {exc}",
                    "status_code": 500,
                }

        return {
            "success": False,
            "error": "Unsplash returned no image",
            "status_code": last_status if last_status else 404,
        }

    def _provider_pexels(self, crop_name: str, stage: Optional[str]) -> Dict[str, Any]:
        api_key = self._next_api_key("pexels")
        if not api_key:
            return {
                "success": False,
                "error": "Pexels key unavailable",
                "status_code": 503,
            }

        last_status = 500
        for query in self._build_crop_queries(crop_name, stage):
            try:
                response = requests.get(
                    "https://api.pexels.com/v1/search",
                    params={"query": query, "per_page": 1},
                    headers={"Authorization": api_key},
                    timeout=8,
                )
                last_status = response.status_code
                if response.status_code == 403:
                    return {
                        "success": False,
                        "error": "Pexels access forbidden",
                        "status_code": 403,
                        "api_key": api_key,
                    }
                if response.status_code != 200:
                    continue

                payload = response.json() or {}
                photos = payload.get("photos") or []
                if not photos:
                    continue
                photo = photos[0]
                src = photo.get("src", {})
                image_url = src.get("large") or src.get("large2x")
                thumb = src.get("tiny") or src.get("medium")
                if image_url:
                    return {
                        "success": True,
                        "image_url": image_url,
                        "thumbnail_url": thumb or image_url,
                        "source": "stock",
                        "provider": "pexels",
                    }
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"Pexels request failed: {exc}",
                    "status_code": 500,
                }

        return {
            "success": False,
            "error": "Pexels returned no image",
            "status_code": last_status if last_status else 404,
        }

    def _provider_pixabay(self, crop_name: str, stage: Optional[str]) -> Dict[str, Any]:
        api_key = self._next_api_key("pixabay")
        last_status = 500

        for query in self._build_crop_queries(crop_name, stage):
            params = {
                "q": query,
                "image_type": "photo",
                "per_page": 1,
                "safesearch": "true",
            }
            if api_key:
                params["key"] = api_key

            try:
                response = requests.get(
                    "https://pixabay.com/api/",
                    params=params,
                    timeout=8,
                )
                last_status = response.status_code
                if response.status_code == 403 and api_key:
                    return {
                        "success": False,
                        "error": "Pixabay access forbidden",
                        "status_code": 403,
                        "api_key": api_key,
                    }
                if response.status_code != 200:
                    continue

                payload = response.json() or {}
                hits = payload.get("hits") or []
                if not hits:
                    continue
                hit = hits[0]
                image_url = hit.get("largeImageURL") or hit.get("webformatURL")
                thumb = hit.get("previewURL") or image_url
                if image_url:
                    return {
                        "success": True,
                        "image_url": image_url,
                        "thumbnail_url": thumb,
                        "source": "stock",
                        "provider": "pixabay",
                    }
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"Pixabay request failed: {exc}",
                    "status_code": 500,
                }

        return {
            "success": False,
            "error": "Pixabay returned no image",
            "status_code": last_status if last_status else 404,
        }


# Backward-compatible alias for existing imports.
ImageService = SmartImageEngine

# ============================================================
# SINGLETON INSTANCE
# ============================================================
_image_service = None


def get_image_service() -> SmartImageEngine:
    """Get singleton SmartImageEngine instance."""
    global _image_service
    if _image_service is None:
        _image_service = SmartImageEngine()
    return _image_service
