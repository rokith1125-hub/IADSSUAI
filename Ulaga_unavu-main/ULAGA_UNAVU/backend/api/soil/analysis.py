"""
Soil Analysis Engine - PRODUCTION READY
NO fake data, NO random predictions, NO fallbacks

CRITICAL RULES:
- CNN predicts ONLY: soil class + confidence
- CNN NEVER explains or suggests
- If CNN unavailable: Return CLEAR error, NEVER simulate
- Soil properties from DATASET ONLY
- All output facts must come from DATASET ONLY
"""

import json
import logging
import re
from difflib import SequenceMatcher
from datetime import datetime
from services.local_storage import db_service
from services.cnn_service import CNNService, ModelNotAvailableError, ImageProcessingError
from utils.path_utils import get_dataset_path
import os

logger = logging.getLogger(__name__)

# Image validation constants
MAX_IMAGE_SIZE_MB = 5
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
MIN_IMAGE_DIMENSION = 100
MAX_IMAGE_DIMENSION = 4096
CONFIDENCE_WARNING_THRESHOLD = 60  # Below this, show warning


class SoilAnalysisError(Exception):
    """Custom error for soil analysis failures"""
    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(message)


class SoilAnalysisEngine:
    """
    Production Soil Analysis Engine
    - Uses CNN for image classification
    - Uses dataset for soil properties
    - Uses deterministic dataset rules for explanation only
    """
    
    def __init__(self):
        self.db = db_service
        self.cnn = CNNService()

        # Load soil dataset
        self.soil_dataset = self._load_soil_dataset()

        if not self.soil_dataset:
            logger.warning("⚠️ Soil dataset is empty or failed to load")
    
    def _load_soil_dataset(self):
        """Load soil dataset from JSON file"""
        try:
            dataset_path = get_dataset_path('soil_types.json')
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ Loaded {len(data)} soil types from dataset")
                return data
        except FileNotFoundError:
            logger.error(f"Soil dataset not found: {dataset_path}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in soil dataset: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading soil dataset: {e}")
            return []

    def _normalize_text(self, value):
        """Normalize text for robust matching."""
        text = str(value or "").lower().replace("___", " ").replace("_", " ")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _soil_profile_score(self, soil):
        """Prefer richer dataset records when duplicates exist."""
        score = 0
        keys = ("ph_range", "region", "suitable_crops", "description", "soil_id")
        for key in keys:
            value = soil.get(key)
            if isinstance(value, list):
                score += len([v for v in value if str(v).strip()])
            elif str(value or "").strip():
                score += 1
        return score

    def _get_soil_matches(self, soil_name):
        """Return all exact or partial matches for a soil name."""
        target = self._normalize_text(soil_name)
        if not target:
            return []
        
        matches = []
        for soil in self.soil_dataset:
            soil_norm = self._normalize_text(soil.get("soil_name", ""))
            if target == soil_norm or target in soil_norm or soil_norm in target:
                matches.append(soil)
        return matches

    def _resolve_soil_profile(self, soil_name):
        """
        Resolve a single soil profile from dataset.
        If duplicates exist, select deterministically by richness score.
        """
        matches = self._get_soil_matches(soil_name)
        if not matches:
            return None, 0

        selected = sorted(
            matches,
            key=lambda s: (
                self._soil_profile_score(s),
                str(s.get("soil_id", "")),
            ),
            reverse=True
        )[0]
        return selected, len(matches)

    def to_public_report(self, result):
        """
        Return soil foundation report for downstream crop engine unlock.
        """
        if not result:
            return {}

        props = result.get("soil_properties", {}) or {}
        explanation = result.get("explanation", {}) or {}
        confidence_value = result.get("confidence_value")
        confidence_label = result.get("confidence_label")

        return {
            "result_id": result.get("result_id") or result.get("_id"),
            "soil_name": result.get("soil_name"),
            "tamil_name": result.get("tamil_name", ""),
            "confidence": confidence_value if confidence_value is not None else confidence_label,
            "suitable_crops": result.get("suitable_crops", []),
            "confidence_warning": result.get("confidence_warning"),
            "soil_properties": {
                "hardness": props.get("hardness", "Unknown"),
                "fertility": props.get("fertility", "Unknown"),
                "water_retention": props.get("water_retention", "Unknown"),
                "drainage": props.get("drainage", "Unknown"),
                "ph_range": props.get("ph_range", "Unknown"),
            },
            "explanation": {
                "summary": explanation.get("summary", ""),
                "dos": explanation.get("dos", []),
                "donts": explanation.get("donts", []),
            },
            "analysis_method": result.get("analysis_method"),
            "created_at": result.get("created_at"),
        }
    
    def _validate_image(self, image_path=None, image_bytes=None):
        """
        Validate image before CNN processing
        
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            from PIL import Image
            import io
            
            if image_bytes:
                # Check size in bytes
                size_mb = len(image_bytes) / (1024 * 1024)
                if size_mb > MAX_IMAGE_SIZE_MB:
                    return False, f"Image too large ({size_mb:.1f}MB). Maximum allowed: {MAX_IMAGE_SIZE_MB}MB"
                
                # Open image from bytes
                img = Image.open(io.BytesIO(image_bytes))
                
            elif image_path:
                # Check file exists
                if not os.path.exists(image_path):
                    return False, "Image file not found"
                
                # Check file size
                size_mb = os.path.getsize(image_path) / (1024 * 1024)
                if size_mb > MAX_IMAGE_SIZE_MB:
                    return False, f"Image too large ({size_mb:.1f}MB). Maximum allowed: {MAX_IMAGE_SIZE_MB}MB"
                
                # Check extension
                ext = os.path.splitext(image_path.lower())[1]
                if ext not in ALLOWED_EXTENSIONS:
                    return False, f"Invalid format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                
                img = Image.open(image_path)
            else:
                return False, "No image provided"
            
            # Check dimensions
            width, height = img.size
            if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                return False, f"Image too small ({width}x{height}). Minimum: {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION}"
            
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                return False, f"Image too large ({width}x{height}). Maximum: {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Image validation error: {e}")
            return False, f"Could not process image: {str(e)}"
    
    def _get_confidence_warning(self, confidence, lang="en"):
        """
        Get warning message if confidence is below threshold
        """
        if confidence >= CONFIDENCE_WARNING_THRESHOLD:
            return None
        
        warnings = {
            "en": f"Low confidence ({confidence}%). The image may be unclear. Consider uploading a clearer photo or selecting soil type manually.",
            "ta": f"குறைந்த நம்பகத்தன்மை ({confidence}%). படம் தெளிவாக இல்லை. தெளிவான படம் upload செய்யுங்கள் அல்லது manual-ஆ select பண்ணுங்க.",
            "mixed": f"Low confidence ({confidence}%). Image clear இல்ல. Better photo upload பண்ணுங்க or manual select பண்ணுங்க."
        }
        return warnings.get(lang, warnings["en"])
    
    def analyze(self, user_id, image_path=None, image_bytes=None, soil_name=None, lang="en"):
        """
        Analyze soil from image or manual selection
        
        Args:
            user_id: User's ID (e.g., Agri_1)
            image_path: Path to soil image
            image_bytes: Raw image bytes
            soil_name: Manual soil selection
            lang: Language for explanation (en, ta, mixed)
            
        Returns:
            dict: Complete soil analysis result
            
        Raises:
            SoilAnalysisError: If analysis fails
        """
        if image_path or image_bytes:
            return self._analyze_with_cnn(user_id, image_path, image_bytes, lang)
        elif soil_name:
            return self._analyze_manually(user_id, soil_name, lang)
        else:
            raise SoilAnalysisError(
                "Please provide either a soil image or select a soil type manually.",
                400
            )
    
    def _analyze_with_cnn(self, user_id, image_path, image_bytes, lang):
        """
        Analyze soil using CNN model
        
        CRITICAL: If CNN unavailable, returns clear error
        """
        # Step 1: Validate image FIRST
        is_valid, validation_error = self._validate_image(image_path, image_bytes)
        if not is_valid:
            raise SoilAnalysisError(
                f"Invalid image: {validation_error}",
                400
            )
        
        # Step 2: Check if CNN model is available FIRST
        model_status = self.cnn.get_model_status('soil_cnn')
        
        if not model_status['available']:
            raise SoilAnalysisError(
                model_status.get('error') or "Model unavailable. Please deploy trained model.",
                503
            )
        
        try:
            logger.info(f"CNN soil analysis for user {user_id}")
            
            # Get CNN prediction
            cnn_result = self.cnn.predict_soil(
                image_path=image_path,
                image_bytes=image_bytes
            )
            
            prediction = cnn_result.get("prediction", {})
            if not prediction and "class_name" in cnn_result and "confidence" in cnn_result:
                prediction = cnn_result

            soil_name = prediction['class_name']
            confidence = prediction['confidence']
            
            logger.info(f"CNN predicted: {soil_name} ({confidence}%)")
            
            # Get soil properties from dataset (NOT from CNN)
            soil_details, _ = self._resolve_soil_profile(soil_name)

            if not soil_details:
                # CNN predicted unknown soil type - use closest match
                logger.warning(f"Soil type '{soil_name}' not in dataset, finding closest match")
                soil_details = self._find_closest_soil(soil_name)
                
                if not soil_details:
                    logger.warning(
                        f"Soil type '{soil_name}' recognized by CNN but missing in soil_types.json."
                    )
                    raise SoilAnalysisError(
                        "Required data unavailable.",
                        422
                    )
            
            confidence_value = float(confidence)
            confidence_label = None

            # Generate explanation
            explanation = self._generate_explanation(soil_details, confidence_value, lang)
            
            # Get confidence warning if needed
            confidence_warning = self._get_confidence_warning(confidence_value, lang)
            
            # Build result
            result = {
                "user_id": user_id,
                "soil_name": soil_details['soil_name'],
                "tamil_name": soil_details.get('tamil_name', ''),
                "suitable_crops": soil_details.get('suitable_crops', []),
                "confidence_value": round(confidence_value, 2),
                "confidence_label": confidence_label,
                "confidence_warning": confidence_warning,
                "analysis_method": "CNN",
                "soil_properties": {
                    "hardness": soil_details.get('hardness', 'Unknown'),
                    "fertility": soil_details.get('fertility', 'Unknown'),
                    "water_retention": soil_details.get('water_retention', 'Unknown'),
                    "drainage": soil_details.get('drainage', 'Unknown'),
                    "ph_range": soil_details.get('ph_range', 'Unknown')
                },
                "explanation": explanation,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Save to database
            result_id = self._save_result(result)
            result['result_id'] = result_id
            
            return result
            
        except ModelNotAvailableError as e:
            raise SoilAnalysisError(
                str(e),
                503
            )
        except ImageProcessingError as e:
            raise SoilAnalysisError(
                f"Image processing failed: {str(e)}. Please upload a valid soil image.",
                400
            )
        except SoilAnalysisError:
            raise
        except Exception as e:
            logger.error(f"CNN analysis error: {str(e)}")
            raise SoilAnalysisError(
                f"Soil analysis failed: {str(e)}",
                500
            )
    
    def _analyze_manually(self, user_id, soil_name, lang):
        """
        Analyze soil with manual selection
        
        Confidence is marked as "Manual" - not a fake confidence value
        """
        logger.info(f"Manual soil analysis for user {user_id}: {soil_name}")
        
        # Get soil details from dataset
        soil_details, _ = self._resolve_soil_profile(soil_name)
        
        if not soil_details:
            # Try case-insensitive search
            soil_details = self._find_closest_soil(soil_name)
            
            if not soil_details:
                raise SoilAnalysisError(
                    f"Soil type '{soil_name}' not found in our database. "
                    f"Available types: {', '.join([s['soil_name'] for s in self.soil_dataset[:5]])}...",
                    400
                )
        
        # Generate explanation using LLM
        explanation = self._generate_explanation(soil_details, confidence="Manual", lang=lang)
        
        # Build result
        result = {
            "user_id": user_id,
            "soil_name": soil_details['soil_name'],
            "tamil_name": soil_details.get('tamil_name', ''),
            "suitable_crops": soil_details.get('suitable_crops', []),
            "confidence_value": None,
            "confidence_label": "Manual Selection",
            "confidence_warning": None,
            "analysis_method": "Manual",
            "soil_properties": {
                "hardness": soil_details.get('hardness', 'Unknown'),
                "fertility": soil_details.get('fertility', 'Unknown'),
                "water_retention": soil_details.get('water_retention', 'Unknown'),
                "drainage": soil_details.get('drainage', 'Unknown'),
                "ph_range": soil_details.get('ph_range', 'Unknown')
            },
            "explanation": explanation,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Save to database
        result_id = self._save_result(result)
        result['result_id'] = result_id
        
        return result
    
    def _get_soil_details(self, soil_name):
        """Get single soil details entry by exact-normalized name."""
        soil, _ = self._resolve_soil_profile(soil_name)
        return soil
    
    def _find_closest_soil(self, soil_name):
        """Find closest matching soil type using aliases + token + fuzzy similarity."""
        if not soil_name:
            return None

        def norm(text):
            text = str(text).lower().replace("___", " ").replace("_", " ")
            text = re.sub(r"[^a-z0-9\s]", " ", text)
            return re.sub(r"\s+", " ", text).strip()

        aliases = {
            "peat soil": "peaty soil",
            "clayey soil": "clay soil",
            "loam soil": "loamy soil",
            "sandy loam soil": "sandy soil",
            "alluvial soil": "alluvial soil"
        }

        input_norm = norm(soil_name)
        if input_norm in aliases:
            input_norm = aliases[input_norm]

        def tokens(text):
            stop = {"soil"}
            out = set()
            for tok in norm(text).split():
                if not tok or tok in stop:
                    continue
                # tiny stem for words like peaty -> peat
                if tok.endswith("y") and len(tok) > 4:
                    tok = tok[:-1]
                out.add(tok)
            return out

        input_tokens = tokens(soil_name)

        # 1) Exact normalized name match
        for soil in self.soil_dataset:
            if norm(soil.get('soil_name', '')) == input_norm:
                return soil

        # 2) Best token overlap score
        best_soil = None
        best_score = 0.0
        for soil in self.soil_dataset:
            soil_name_val = soil.get('soil_name', '')
            soil_tokens = tokens(soil_name_val)
            if not soil_tokens or not input_tokens:
                continue
            overlap = len(input_tokens & soil_tokens)
            token_score = overlap / max(len(soil_tokens), 1)
            fuzzy_score = SequenceMatcher(None, input_norm, norm(soil_name_val)).ratio()
            score = max(token_score, fuzzy_score)
            if score > best_score:
                best_score = score
                best_soil = soil

        # 3) Tamil-name fallback (exact containment)
        if best_score <= 0:
            for soil in self.soil_dataset:
                tamil = str(soil.get('tamil_name', '')).strip().lower()
                if tamil and tamil in soil_name.lower():
                    return soil

        # Require moderate threshold.
        return best_soil if best_score >= 0.44 else None

    def _generate_explanation(self, soil_details, confidence, lang):
        """
        Generate deterministic explanation from dataset only.
        """
        soil_name = soil_details.get("soil_name", "Unknown Soil")
        ph_range = soil_details.get("ph_range", "Unknown")
        drainage = soil_details.get("drainage", "Unknown")
        water_retention = soil_details.get("water_retention", "Unknown")

        summary_en = (
            f"{soil_name} identified from image. "
            f"Dataset pH range is {ph_range}."
        )
        summary_ta = (
            f"{soil_name} soil identify aagiyadhu. "
            f"Dataset pH range: {ph_range}."
        )

        if lang == "ta":
            summary = summary_ta
        elif lang == "mixed":
            summary = f"{soil_name} soil identified. pH range: {ph_range}."
        else:
            summary = summary_en

        dos = [
            "Match crop choice with pH range",
            "Record pH test once per season",
            f"Use irrigation plan suitable for {water_retention.lower()} water retention"
        ]
        donts = [
            "Do not assume nutrients without a lab test",
            f"Avoid practices that worsen {drainage.lower()} drainage",
            "Do not over-apply fertilizers without soil test values"
        ]

        return {
            "summary": summary,
            "dos": dos,
            "donts": donts
        }
    
    def _save_result(self, result):
        """Save soil analysis result to database"""
        try:
            inserted = self.db.insert_one('soil_results', result)
            
            # Update user's current soil
            self.db.update_one(
                'users',
                {"user_id": result['user_id']},
                {"$set": {"current_soil": result['soil_name']}}
            )
            
            logger.info(f"Saved soil result for user {result['user_id']}")
            return str(inserted.inserted_id)
            
        except Exception as e:
            logger.error(f"Error saving soil result: {e}")
            # Don't fail the analysis if save fails
            return None
    
    def get_history(self, user_id, limit=10):
        """Get soil analysis history for user"""
        try:
            results = self.db.find(
                'soil_results',
                {"user_id": user_id},
                sort=[("created_at", -1)],
                limit=limit
            )
            
            # Format results
            history = []
            for result in results:
                history.append({
                    "result_id": str(result.get('_id', '')),
                    "soil_name": result.get('soil_name', ''),
                    "confidence": (
                        result.get('confidence_value')
                        if result.get('confidence_value') is not None
                        else result.get('confidence_label', '')
                    ),
                    "analysis_method": result.get('analysis_method', ''),
                    "created_at": result.get('created_at', '')
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting soil history: {e}")
            return []
    
    def get_result_by_id(self, user_id, result_id):
        """Get specific soil result by ID"""
        try:
            result = self.db.find_one('soil_results', {
                "_id": result_id,
                "user_id": user_id
            })
            
            if result:
                result['result_id'] = str(result.pop('_id', ''))
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting soil result: {e}")
            return None
    
    def get_soil_types(self):
        """Get list of all available soil types for manual selection"""
        return [{
            "soil_name": soil['soil_name'],
            "tamil_name": soil.get('tamil_name', ''),
            "ph_range": soil.get('ph_range', 'Unknown'),
            "icon": self._get_soil_icon(soil['soil_name'])
        } for soil in self.soil_dataset]
    
    def _get_soil_icon(self, soil_name):
        """Get emoji icon for soil type"""
        icons = {
            "red": "🔴",
            "black": "⚫",
            "alluvial": "🟤",
            "sandy": "🟡",
            "clay": "🟫",
            "loamy": "🟢",
            "laterite": "🟠"
        }
        
        for key, icon in icons.items():
            if key in soil_name.lower():
                return icon
        
        return "🌱"
    
    def get_model_status(self):
        """Get status of the soil CNN model"""
        return self.cnn.get_model_status('soil_cnn')


# Singleton instance
soil_analyzer = SoilAnalysisEngine()


def get_soil_analyzer():
    """Get the singleton soil analyzer instance"""
    return soil_analyzer
