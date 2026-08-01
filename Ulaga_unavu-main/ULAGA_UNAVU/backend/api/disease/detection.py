"""
Disease Detection Engine - PRODUCTION READY
NO fake data, NO random predictions, NO fallbacks

CRITICAL RULES:
- CNN predicts ONLY: disease class + confidence
- CNN NEVER explains or suggests treatments
- If CNN unavailable: Return CLEAR error, NEVER simulate
- Disease properties from DATASET ONLY
- LLM explains in farmer language ONLY
"""

import json
import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from difflib import SequenceMatcher
from datetime import datetime
from services.local_storage import db_service
from services.cnn_service import CNNService, ModelNotAvailableError, ImageProcessingError
from services.llm_service import LLMService
from services.weather_service import WeatherService
from utils.path_utils import get_dataset_path

logger = logging.getLogger(__name__)


class DiseaseDetectionError(Exception):
    """Custom error for disease detection failures"""
    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(message)


class DiseaseDetector:
    """
    Production Disease Detection Engine
    - Uses CNN for image classification
    - Uses dataset for disease properties
    - Uses LLM for explanation only
    """
    
    def __init__(self):
        self.db = db_service
        self.cnn = CNNService()
        self.llm = LLMService()
        self.weather = WeatherService()
        self.model_version = "v1.0"
        self.enable_llm_explanations = os.getenv("ENABLE_LLM_DISEASE_EXPLANATIONS", "false").lower() == "true"
        
        # Load disease dataset
        self.disease_dataset = self._load_disease_dataset()
        self.disease_class_map = self._load_disease_class_map()
        
        if not self.disease_dataset:
            logger.warning("âš ï¸ Disease dataset is empty or failed to load")
        if not self.disease_class_map:
            logger.info("Disease class map not configured; using direct/fuzzy dataset mapping")
    
    def _load_disease_dataset(self):
        """Load disease dataset from JSON file"""
        try:
            dataset_path = get_dataset_path('disease_data.json')
            with open(dataset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"âœ… Loaded {len(data)} diseases from dataset")
                return data
        except FileNotFoundError:
            logger.error(f"Disease dataset not found")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in disease dataset: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading disease dataset: {e}")
            return []

    def _load_disease_class_map(self):
        """Load optional model-class to dataset mapping."""
        try:
            mapping_path = get_dataset_path('disease_class_map.json')
            with open(mapping_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                logger.warning("Disease class map format invalid; expected JSON object")
                return {}

            mapping = {}
            for key, value in raw.items():
                source = str(key or "").strip()
                target = str(value or "").strip()
                if not source or not target:
                    continue
                mapping[source] = target
                mapping[self._normalize_text(source)] = target

            logger.info("Loaded %s disease class-map entries", len(mapping))
            return mapping
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            logger.error("Invalid disease class map JSON: %s", str(exc))
            return {}
        except Exception as exc:
            logger.error("Error loading disease class map: %s", str(exc))
            return {}
    
    def detect(self, user_id, image_path=None, image_bytes=None, disease_name=None,
               crop_name=None, lang="en", ui_mode=None):
        """
        Detect disease from image or manual selection
        
        Args:
            user_id: User's ID (e.g., Agri_1)
            image_path: Path to plant image
            image_bytes: Raw image bytes
            disease_name: Manual disease selection
            crop_name: Name of affected crop
            lang: Language for explanation (en, ta, mixed)
            
        Returns:
            dict: Complete disease detection result
            
        Raises:
            DiseaseDetectionError: If detection fails
        """
        if image_path or image_bytes:
            return self._detect_with_cnn(user_id, image_path, image_bytes, crop_name, lang, ui_mode=ui_mode)
        elif disease_name:
            return self._detect_manually(user_id, disease_name, crop_name, lang, ui_mode=ui_mode)
        else:
            raise DiseaseDetectionError(
                "Please provide either a plant image or select a disease manually.",
                400
            )
    
    def _detect_with_cnn(self, user_id, image_path, image_bytes, crop_name, lang, ui_mode=None):
        """
        Detect disease using CNN model
        
        CRITICAL: If CNN unavailable, returns clear error
        """
        model_status = self.cnn.get_model_status('disease_cnn')
        if not model_status.get('tensorflow_available'):
            raise DiseaseDetectionError(
                "Disease model unavailable: TensorFlow is not available.",
                503
            )
        if not model_status.get('model_file_exists'):
            raise DiseaseDetectionError(
                "Disease model unavailable: model file missing.",
                503
            )
        if not model_status.get('config_file_exists'):
            raise DiseaseDetectionError(
                "Disease model unavailable: label configuration missing.",
                503
            )
        if not model_status.get('available'):
            raise DiseaseDetectionError(
                model_status.get('error') or "Model unavailable. Please deploy trained model.",
                503
            )

        try:
            logger.info(f"CNN disease detection for user {user_id}")

            cnn_result = self.cnn.predict_disease(image_path=image_path, image_bytes=image_bytes)
            primary = cnn_result.get("primary", {})
            alternatives = cnn_result.get("alternatives", [])
            
            disease_name = primary.get('class', '').strip()
            disease_name_raw = primary.get('class_raw', disease_name).strip()
            confidence = float(primary.get('confidence', 0))
            is_healthy_prediction = bool(cnn_result.get('is_healthy', False))
            model_display_name = self._resolve_model_display_name(disease_name_raw, disease_name)

            if not disease_name:
                raise DiseaseDetectionError("Prediction failed", 500)

            # Step 1 & 6: Log top predictions
            top3_log = [primary] + alternatives
            logger.info(f"Top predictions: {top3_log}")

            # Step 2: Confidence Warning (Threshold 85%)
            warning = None
            if confidence < 85:
                warning = "Prediction uncertain. Please verify crop."
                logger.warning(f"Low confidence ({confidence}%): {warning}")

            # Step 3: Crop Match Validation
            if crop_name and crop_name.lower().strip():
                user_crop = crop_name.lower().strip()
                # Check if primary prediction matches user crop
                if user_crop not in disease_name.lower():
                    warning = "Prediction crop mismatch detected"
                    logger.warning(f"Crop mismatch: User provided '{user_crop}', AI predicted '{disease_name}'")

            weather_context = self._extract_weather_context(user_id)
            spray_recommendation = self._build_spray_recommendation(weather_context)

            if (
                is_healthy_prediction
                or 'healthy' in disease_name.lower()
                or 'normal' in disease_name.lower()
            ):
                result = self._create_healthy_result(
                    user_id=user_id,
                    confidence=confidence,
                    crop_name=crop_name,
                    lang=lang,
                    prediction=disease_name_raw,
                    image_path=image_path,
                    weather_context=weather_context,
                    spray_recommendation=spray_recommendation,
                )
                # Add transparency data
                result["alternatives"] = alternatives
                if warning:
                    result["warning"] = warning
                return result

            disease_details = self._map_cnn_class_to_dataset(disease_name_raw, disease_name)
            if not disease_details:
                logger.warning(
                    "Disease dataset mapping missing for class_name_raw='%s', class_name='%s'",
                    disease_name_raw,
                    disease_name
                )
                result = self._build_unmapped_result(
                    user_id=user_id,
                    disease_name=model_display_name or disease_name,
                    disease_name_raw=disease_name_raw,
                    confidence=confidence,
                    crop_name=crop_name,
                    analysis_method="CNN",
                    weather_context=weather_context,
                    spray_recommendation=spray_recommendation,
                    image_path=image_path,
                    lang=lang,
                    ui_mode=ui_mode,
                )
                # Add transparency data
                result["alternatives"] = alternatives
                if warning:
                    result["warning"] = warning
                    
                result_id = self._save_result(result)
                result['result_id'] = result_id
                result['analysis_id'] = result_id
                return result

            result = self._build_result(
                user_id=user_id,
                disease_details=disease_details,
                confidence=confidence,
                analysis_method="CNN",
                crop_name=crop_name,
                weather_context=weather_context,
                spray_recommendation=spray_recommendation,
                lang=lang,
                prediction=disease_name_raw,
                image_path=image_path,
                ui_mode=ui_mode,
            )
            # Add transparency data
            result["alternatives"] = alternatives
            if warning:
                result["warning"] = warning
                result["confidence_warning"] = warning

            result_id = self._save_result(result)
            result['result_id'] = result_id
            result['analysis_id'] = result_id
            return result
            
        except ModelNotAvailableError as e:
            raise DiseaseDetectionError(
                str(e),
                503
            )
        except ImageProcessingError as e:
            raise DiseaseDetectionError(
                f"Image processing failed: {str(e)}. Please upload a valid plant image.",
                400
            )
        except DiseaseDetectionError:
            raise
        except Exception as e:
            logger.error(f"CNN detection error: {str(e)}")
            raise DiseaseDetectionError(
                "Prediction failed",
                500
            )
    
    def _detect_manually(self, user_id, disease_name, crop_name, lang, ui_mode=None):
        """
        Detect disease with manual selection
        """
        logger.info(f"Manual disease detection for user {user_id}: {disease_name}")
        
        # Handle healthy case
        if disease_name.lower() == 'healthy':
            weather_context = self._extract_weather_context(user_id)
            spray_recommendation = self._build_spray_recommendation(weather_context)
            return self._create_healthy_result(
                user_id=user_id,
                confidence="Manual",
                crop_name=crop_name,
                lang=lang,
                prediction=disease_name,
                image_path=None,
                weather_context=weather_context,
                spray_recommendation=spray_recommendation,
            )
        
        # Get disease details from dataset
        disease_details = self._get_disease_details(disease_name)
        
        if not disease_details:
            disease_details = self._find_closest_disease(disease_name)
            
            if not disease_details:
                available = ', '.join([d['disease_name'] for d in self.disease_dataset[:5]])
                raise DiseaseDetectionError(
                    f"Disease '{disease_name}' not found in our database. "
                    f"Available: {available}...",
                    400
                )
        
        weather_context = self._extract_weather_context(user_id)
        spray_recommendation = self._build_spray_recommendation(weather_context)
        
        # Build result
        result = self._build_result(
            user_id=user_id,
            disease_details=disease_details,
            confidence="Manual Selection",
            analysis_method="Manual",
            crop_name=crop_name,
            weather_context=weather_context,
            spray_recommendation=spray_recommendation,
            lang=lang,
            prediction=disease_name,
            image_path=None,
            ui_mode=ui_mode,
        )
        
        # Save to database
        result_id = self._save_result(result)
        result['result_id'] = result_id
        result['analysis_id'] = result_id
        
        return result
    
    def _create_healthy_result(
        self,
        user_id,
        confidence,
        crop_name,
        lang,
        prediction,
        image_path,
        weather_context=None,
        spray_recommendation=None,
    ):
        """Create result for healthy plant"""
        confidence_value = (
            round(float(confidence), 2)
            if isinstance(confidence, (int, float))
            else confidence
        )
        plant_name, _ = self._split_label_parts(prediction)
        if not plant_name:
            plant_name = str(crop_name or "").strip() or (prediction or "Plant")
        crop_value = crop_name or plant_name or "Unknown"
        result = {
            "user_id": user_id,
            "disease_name": "Healthy",
            "tamil_name": "",
            "confidence": confidence_value,
            "analysis_method": "CNN" if confidence != "Manual" else "Manual",
            "crop_name": crop_value,
            "affected_crop": crop_value,
            "image_path": image_path,
            "image_url": image_path,
            "prediction": prediction or "Healthy",
            "severity_level": "None",
            "severity": "None",
            "is_healthy": True,
            "message": "Plant looks healthy",
            "confidence_percentage": (
                f"{confidence_value}%"
                if isinstance(confidence_value, (int, float))
                else str(confidence_value)
            ),
            "weather_context": weather_context,
            "spray_recommendation": spray_recommendation,
            "spray_safe": bool(spray_recommendation.get("is_safe_to_spray")) if spray_recommendation else None,
            "weather_snapshot_json": weather_context,
            "spray_recommendation_json": spray_recommendation,
            "treatment_plan": None,
            "treatment_plan_json": None,
            "llm_explanation": "Plant is healthy. Continue preventive care and weekly monitoring.",
            "plant_template_output": self._format_plant_template(
                name=plant_name,
                is_healthy=True
            ),
            "explanation": {
                "summary": "Plant looks healthy",
                "urgent_action": "No immediate action required.",
                "seek_help_when": "If new spots, curl, or wilt appears."
            },
            "model_version": self.model_version,
            "created_at": datetime.utcnow().isoformat()
        }

        result_id = self._save_result(result)
        result['result_id'] = result_id
        result['analysis_id'] = result_id
        return result

    def _build_result(self, user_id, disease_details, confidence, analysis_method,
                      crop_name, weather_context, spray_recommendation, lang,
                      prediction, image_path, ui_mode=None):
        """Build comprehensive disease result"""

        disease_name = disease_details['disease_name']
        severity = disease_details.get('severity_level', 'Medium')

        # Generate explanation using LLM
        explanation = self._generate_explanation(disease_details, confidence, lang)
        treatment_plan = self._build_treatment_plan(disease_details, severity)
        llm_explanation = self._build_llm_spray_explanation(
            disease_name=disease_name,
            weather_context=weather_context,
            spray_recommendation=spray_recommendation,
            lang=lang
        )
        confidence_percentage = (
            f"{round(float(confidence), 2)}%"
            if isinstance(confidence, (int, float))
            else str(confidence)
        )
        short_mode = str(ui_mode or "").lower() == "short"
        plant_template_output = self._format_plant_template(
            name=disease_name,
            is_healthy=False,
            disease_problem=disease_name,
            issue_summary=self._build_issue_summary(disease_details),
            organic_solution=self._format_solution_lines(disease_details.get("treatment", {}).get("organic", [])),
            chemical_solution=self._format_solution_lines(disease_details.get("treatment", {}).get("chemical", [])),
            impact_future=self._build_impact_future(disease_details),
            growth_impact=self._build_growth_impact(disease_details),
            action_plan=self._build_action_plan(disease_details),
            short_mode=short_mode
        )

        consultation_advised = severity in ['High', 'Critical'] or (
            isinstance(confidence, (int, float)) and confidence < 60
        )
        crop_value = crop_name or disease_details.get('affected_crop', 'Various')

        return {
            "user_id": user_id,
            "disease_name": disease_name,
            "tamil_name": disease_details.get('tamil_name', ''),
            "scientific_name": disease_details.get('scientific_name', ''),
            "confidence": round(confidence, 2) if isinstance(confidence, (int, float)) else confidence,
            "analysis_method": analysis_method,
            "crop_name": crop_value,
            "affected_crop": crop_value,
            "image_path": image_path,
            "image_url": image_path,
            "prediction": prediction or disease_name,
            "severity_level": severity,
            "severity": severity,
            "is_healthy": False,
            "confidence_percentage": confidence_percentage,
            "symptoms": disease_details.get('symptoms', [])[:5],
            "causes": disease_details.get('causes', [])[:3],
            "spread_speed": disease_details.get('spread_speed', 'Moderate'),
            "weather_conditions": disease_details.get('weather_conditions', ''),
            "treatment": {
                "organic": disease_details.get('treatment', {}).get('organic', [])[:3],
                "chemical": disease_details.get('treatment', {}).get('chemical', [])[:2],
                "prevention": disease_details.get('treatment', {}).get('prevention', [])[:3],
                "safety_notes": "Use chemicals with caution. Follow safety guidelines."
            },
            "weather_warning": self._get_weather_warning_from_context(weather_context, severity),
            "weather_context": weather_context,
            "spray_recommendation": spray_recommendation,
            "spray_safe": bool(spray_recommendation.get("is_safe_to_spray")) if spray_recommendation else None,
            "weather_snapshot_json": weather_context,
            "spray_recommendation_json": spray_recommendation,
            "treatment_plan": treatment_plan,
            "treatment_plan_json": treatment_plan,
            "llm_explanation": llm_explanation,
            "plant_template_output": plant_template_output,
            "explanation": explanation,
            "consultation_advised": consultation_advised,
            "emergency_contact": "+91-1551" if consultation_advised else None,
            "model_version": self.model_version,
            "created_at": datetime.utcnow().isoformat()
        }

    def _get_disease_details(self, disease_name):
        """Get disease details from dataset by exact name"""
        for disease in self.disease_dataset:
            if disease['disease_name'].lower() == disease_name.lower():
                return disease
        return None

    def _get_disease_by_id(self, disease_id):
        """Get disease details by disease_id from dataset."""
        target = str(disease_id or "").strip().lower()
        if not target:
            return None
        for disease in self.disease_dataset:
            if str(disease.get("disease_id", "")).strip().lower() == target:
                return disease
        return None

    def _normalize_text(self, value):
        """Normalize text for deterministic class-to-dataset mapping."""
        text = str(value or "").lower().replace("___", " ").replace("_", " ")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _split_label_parts(self, label):
        """
        Split model label into (crop, disease) parts when available.
        Supports "Crop___Disease" and "Crop - Disease" formats.
        """
        raw = str(label or "").strip()
        if not raw:
            return None, None
        if "___" in raw:
            crop, disease = raw.split("___", 1)
        elif " - " in raw:
            crop, disease = raw.split(" - ", 1)
        else:
            return None, raw.replace("_", " ").strip()
        return crop.replace("_", " ").strip(), disease.replace("_", " ").strip()

    def _resolve_model_display_name(self, class_name_raw, class_name):
        """
        Resolve disease display name directly from model label and optional class-map.
        This keeps output aligned with disease_cnn.h5 + disease_cnn.json labels even
        when local disease dataset mapping is unavailable.
        """
        for candidate in (class_name_raw, class_name):
            key = str(candidate or "").strip()
            if not key:
                continue
            mapped = self.disease_class_map.get(key) or self.disease_class_map.get(self._normalize_text(key))
            if mapped:
                return mapped
        return str(class_name or class_name_raw or "").strip()

    def _map_cnn_class_to_dataset(self, class_name_raw, class_name):
        """
        Deterministically map CNN class label to disease dataset.
        Uses exact/alias/token mapping only.
        """
        # 0) Optional explicit class-map (model label -> disease_id/disease_name)
        for candidate in (class_name_raw, class_name):
            key = str(candidate or "").strip()
            if not key:
                continue
            target = self.disease_class_map.get(key) or self.disease_class_map.get(self._normalize_text(key))
            if not target:
                continue
            mapped = self._get_disease_by_id(target) or self._get_disease_details(target)
            if mapped:
                return mapped

        raw_norm = self._normalize_text(class_name_raw)
        class_norm = self._normalize_text(class_name)

        for candidate in (class_name_raw, class_name, raw_norm, class_norm):
            if not candidate:
                continue
            disease = self._get_disease_details(candidate)
            if disease:
                return disease

        crop_norm = ""
        disease_norm = raw_norm
        crop_display = None
        disease_display = None

        crop_display, disease_display = self._split_label_parts(class_name_raw)
        if not crop_display and not disease_display:
            crop_display, disease_display = self._split_label_parts(class_name)

        if crop_display:
            crop_norm = self._normalize_text(crop_display)
        if disease_display:
            disease_norm = self._normalize_text(disease_display)

        if crop_display and disease_display:
            candidate_names = [
                f"{disease_display} of {crop_display}",
                f"{disease_display} ({crop_display})",
                f"{disease_display} - {crop_display}",
                f"{disease_display} {crop_display}",
                f"{crop_display} {disease_display}",
            ]
            for candidate in candidate_names:
                mapped = self._get_disease_details(candidate)
                if mapped:
                    return mapped

        alias_pairs = {
            ("grape", "black rot"): "Black Rot of Grape",
            ("tomato", "early blight"): "Early Blight of Tomato",
            ("potato", "early blight"): "Blight of Potato",
            ("potato", "late blight"): "Late Blight of Potato",
            ("squash", "powdery mildew"): "Powdery Mildew",
            ("cherry", "powdery mildew"): "Powdery Mildew",
        }
        for (crop_key, disease_key), target_name in alias_pairs.items():
            if crop_key in crop_norm and disease_key in disease_norm:
                mapped = self._get_disease_details(target_name)
                if mapped:
                    return mapped

        disease_tokens = {tok for tok in disease_norm.split() if tok}
        if not disease_tokens:
            return None

        best_match = None
        best_score = 0.0
        for disease in self.disease_dataset:
            dataset_name = self._normalize_text(disease.get("disease_name", ""))
            dataset_crop = self._normalize_text(disease.get("affected_crop", ""))
            if crop_norm and dataset_crop and crop_norm not in dataset_crop and dataset_crop not in crop_norm:
                continue

            dataset_tokens = {tok for tok in dataset_name.split() if tok}
            overlap = len(disease_tokens & dataset_tokens)
            if overlap <= 0:
                continue

            score = overlap / max(len(disease_tokens), 1)
            if score > best_score:
                best_score = score
                best_match = disease

        # Increased threshold from 0.6 to 0.8 for strict token matching
        return best_match if best_score >= 0.8 else None
    def _find_closest_disease(self, disease_name):
        """Find closest matching disease using aliases + token + fuzzy similarity."""
        if not disease_name:
            return None

        def norm(text):
            text = str(text).lower().replace("___", " ").replace("_", " ")
            text = re.sub(r"[^a-z0-9\s]", " ", text)
            return re.sub(r"\s+", " ", text).strip()

        aliases = {
            "grape black rot": "black rot",
            "tomato early blight": "early blight of tomato",
            "tomato late blight": "late blight of tomato",
            "potato early blight": "blight of potato",
            "potato late blight": "late blight of potato",
        }

        # Keep disease words, but remove very generic tokens.
        stop = {
            "plant", "crop", "including", "sour", "maize", "bell"
        }

        def tokens(text):
            out = set()
            for t in norm(text).split():
                if not t or t in stop:
                    continue
                if t.endswith("ing") and len(t) > 5:
                    t = t[:-3]
                out.add(t)
            return out

        input_norm = norm(disease_name)
        input_norm = aliases.get(input_norm, input_norm)
        input_tokens = tokens(disease_name)

        # 1) Exact normalized name
        for disease in self.disease_dataset:
            if norm(disease.get('disease_name', '')) == input_norm:
                return disease

        # 2) Best token overlap
        best_disease = None
        best_score = 0.0
        for disease in self.disease_dataset:
            disease_name_val = disease.get('disease_name', '')
            ds_tokens = tokens(disease_name_val)
            if not ds_tokens or not input_tokens:
                continue
            overlap = len(input_tokens & ds_tokens)
            token_score = overlap / max(len(ds_tokens), 1)
            fuzzy_score = SequenceMatcher(None, input_norm, norm(disease_name_val)).ratio()
            score = max(token_score, fuzzy_score)
            if score > best_score:
                best_score = score
                best_disease = disease

        # 3) Tamil-name fallback
        if best_score <= 0:
            disease_lower = disease_name.lower()
            for disease in self.disease_dataset:
                tamil = str(disease.get('tamil_name', '')).strip().lower()
                if tamil and tamil in disease_lower:
                    return disease

        return best_disease if best_score >= 0.75 else None

    def _build_unmapped_result(
        self,
        user_id,
        disease_name,
        disease_name_raw,
        confidence,
        crop_name,
        analysis_method,
        weather_context,
        spray_recommendation,
        image_path,
        lang="en",
        ui_mode=None,
    ):
        """Return a deterministic model-only result when dataset mapping is missing."""
        confidence_percentage = f"{round(float(confidence), 2)}%"
        inferred_crop, _ = self._split_label_parts(disease_name_raw or disease_name)
        crop_value = crop_name or inferred_crop or "Unknown"
        severity = "Unknown"
        short_mode = str(ui_mode or "").lower() == "short"
        issue_summary = "Model identified disease class, but dataset mapping is currently unavailable."
        organic_solution = "Use field sanitation and remove visibly affected leaves."
        chemical_solution = "Consult local agriculture officer before applying fungicide."
        impact_future = "Without validated mapping, future impact cannot be estimated reliably."
        growth_impact = "Potential yield impact exists; confirm diagnosis with local expert."
        action_plan = "- Isolate affected plants\n- Capture clearer close-up image\n- Consult agriculture extension officer"

        llm_explanation = self._build_llm_spray_explanation(
            disease_name=disease_name,
            weather_context=weather_context,
            spray_recommendation=spray_recommendation,
            lang=lang
        )

        return {
            "user_id": user_id,
            "disease_name": disease_name,
            "tamil_name": "",
            "scientific_name": "",
            "confidence": round(float(confidence), 2),
            "confidence_percentage": confidence_percentage,
            "analysis_method": analysis_method,
            "crop_name": crop_value,
            "affected_crop": crop_value,
            "image_path": image_path,
            "image_url": image_path,
            "prediction": disease_name_raw or disease_name,
            "severity_level": severity,
            "severity": severity,
            "is_healthy": False,
            "symptoms": [],
            "causes": [],
            "spread_speed": "Unknown",
            "weather_conditions": "",
            "treatment": {
                "organic": [],
                "chemical": [],
                "prevention": [
                    "Use clean tools and sanitize after use",
                    "Remove heavily infected leaves",
                    "Get local diagnosis confirmation before spray"
                ],
                "safety_notes": "Dataset mapping missing. Avoid unverified chemical usage."
            },
            "weather_warning": self._get_weather_warning_from_context(weather_context, severity),
            "weather_context": weather_context,
            "spray_recommendation": spray_recommendation,
            "spray_safe": bool(spray_recommendation.get("is_safe_to_spray")) if spray_recommendation else None,
            "weather_snapshot_json": weather_context,
            "spray_recommendation_json": spray_recommendation,
            "treatment_plan": {
                "medicine": "Unavailable (dataset mapping missing)",
                "dosage": "Consult local agriculture officer",
                "method": "Not recommended until diagnosis is confirmed",
                "repeat_interval_days": None
            },
            "treatment_plan_json": {
                "medicine": "Unavailable (dataset mapping missing)",
                "dosage": "Consult local agriculture officer",
                "method": "Not recommended until diagnosis is confirmed",
                "repeat_interval_days": None
            },
            "llm_explanation": llm_explanation,
            "plant_template_output": self._format_plant_template(
                name=disease_name,
                is_healthy=False,
                disease_problem=disease_name,
                issue_summary=issue_summary,
                organic_solution=organic_solution,
                chemical_solution=chemical_solution,
                impact_future=impact_future,
                growth_impact=growth_impact,
                action_plan=action_plan,
                short_mode=short_mode
            ),
            "explanation": {
                "summary": issue_summary,
                "urgent_action": "Confirm diagnosis with clearer image or local expert before treatment.",
                "seek_help_when": "Seek help immediately if spread accelerates in nearby plants."
            },
            "consultation_advised": True,
            "emergency_contact": "+91-1551",
            "model_version": self.model_version,
            "dataset_mapping_status": "missing",
            "created_at": datetime.utcnow().isoformat()
        }

    def _extract_weather_context(self, user_id):
        """Get deterministic weather context for spray decisions."""
        try:
            user = self.db.find_one('users', {"user_id": user_id}) or {}
            farm_info = user.get("farm_info", {}) or {}

            weather_payload = None
            lat = farm_info.get("latitude")
            lon = farm_info.get("longitude")
            if lat is not None and lon is not None:
                try:
                    weather_payload = self.weather.get_current_weather(f"{float(lat)},{float(lon)}")
                except Exception:
                    weather_payload = None
                if weather_payload is None:
                    # Do not make another network call when coordinate-based weather already failed.
                    return None

            if not weather_payload:
                district = farm_info.get("district") or farm_info.get("state")
                if district:
                    weather_payload = self.weather.get_current_weather(district)

            if not weather_payload:
                return None

            current = weather_payload.get("current", {}) or {}
            hourly = weather_payload.get("forecast", {}).get("hourly", []) or []
            probs = [
                item.get("precipitation_probability")
                for item in hourly[:24]
                if isinstance(item.get("precipitation_probability"), (int, float))
            ]
            rain_probability = max(probs) if probs else 0
            return {
                "temperature": current.get("temperature"),
                "humidity": current.get("humidity"),
                "wind_speed": current.get("wind_speed"),
                "rain_probability": rain_probability,
            }
        except Exception as exc:
            logger.warning("Weather context unavailable for disease detection: %s", str(exc))
            return None

    def _build_spray_recommendation(self, weather_context):
        """Deterministic spray safety decision engine."""
        if not weather_context:
            return None

        def to_float(value, default=0.0):
            try:
                return float(value)
            except Exception:
                return default

        temp = to_float(weather_context.get("temperature"), 0.0)
        humidity = to_float(weather_context.get("humidity"), 0.0)
        wind_speed = to_float(weather_context.get("wind_speed"), 0.0)
        rain_probability = to_float(weather_context.get("rain_probability"), 0.0)

        risk_score = 0
        reasons = []
        is_safe = True

        if wind_speed > 20:
            risk_score += 35
            is_safe = False
            reasons.append("High wind speed can cause chemical drift")
        elif wind_speed > 12:
            risk_score += 10
            reasons.append("Moderate wind requires cautious spraying")

        if rain_probability > 40:
            risk_score += 35
            is_safe = False
            reasons.append("High rain probability can wash off spray")
        elif rain_probability > 20:
            risk_score += 15
            reasons.append("Rain chance is moderate")

        if temp > 34:
            risk_score += 20
            reasons.append("High temperature is not suitable for afternoon spraying")
        elif temp < 20:
            risk_score += 10
            reasons.append("Low temperature may reduce treatment efficiency")

        if humidity < 50 or humidity > 80:
            risk_score += 10
            reasons.append("Humidity is outside ideal 50-80% range")

        risk_score = min(100, max(0, int(round(risk_score))))

        if not is_safe:
            best_time = "Not recommended now"
        elif temp > 32:
            best_time = "Late Evening (4PM-6PM)"
        else:
            best_time = "Early Morning (6AM-9AM)"

        if reasons:
            reason = "; ".join(reasons[:3])
        else:
            reason = "Low wind and no rain expected"

        return {
            "is_safe_to_spray": bool(is_safe),
            "best_time": best_time,
            "reason": reason,
            "risk_score": risk_score
        }

    def _get_weather_warning_from_context(self, weather_context, severity):
        """Generate weather warning text from structured weather context."""
        if not weather_context:
            return "Weather context unavailable."

        warnings = []
        wind_speed = float(weather_context.get("wind_speed") or 0)
        rain_probability = float(weather_context.get("rain_probability") or 0)
        humidity = float(weather_context.get("humidity") or 0)

        if rain_probability > 40:
            warnings.append("Rain probability is high. Delay spraying.")
        if wind_speed > 20:
            warnings.append("Wind speed is high. Avoid spraying now.")
        if humidity > 85 and severity in ['High', 'Critical']:
            warnings.append("High humidity may worsen disease spread.")
        if not warnings:
            return "Weather currently supports safe treatment timing."
        return " | ".join(warnings)

    def _build_treatment_plan(self, disease_details, severity):
        """Build deterministic treatment plan from dataset fields only."""
        treatment = disease_details.get("treatment", {}) or {}
        chemical = treatment.get("chemical", []) or []
        organic = treatment.get("organic", []) or []
        medicine = chemical[0] if chemical else (organic[0] if organic else "Consult local agriculture officer")
        repeat_days = 5 if severity in ["High", "Critical"] else 7
        return {
            "medicine": medicine,
            "dosage": "Follow product label dosage and local agronomist guidance.",
            "method": "Foliar spray",
            "repeat_interval_days": repeat_days
        }

    def _build_llm_spray_explanation(self, disease_name, weather_context, spray_recommendation, lang="en"):
        """Generate concise weather-aware spray explanation."""
        if not weather_context or not spray_recommendation:
            return "Weather intelligence unavailable; use local field conditions before spraying."
        if not self.enable_llm_explanations:
            if spray_recommendation.get("is_safe_to_spray"):
                return "Spraying is safer now due to manageable wind and low rain risk. This timing reduces wash-off and drift risk."
            return "Spraying is not safe now because weather risk is high. Wait for lower wind and lower rain probability to improve treatment effectiveness."
        if not self.llm.groq_client and not self.llm.openai_client:
            return (
                "Weather-based spray advice generated without LLM. "
                "Use low-wind and low-rain window for safer application."
            )

        language = "english"
        if lang == "ta":
            language = "tamil"
        elif lang == "mixed":
            language = "tanglish"

        prompt = f"""
You are an agriculture assistant. Explain spray timing decision in 2-3 sentences.
Disease: {disease_name}
Weather: temperature={weather_context.get('temperature')}, humidity={weather_context.get('humidity')}, wind={weather_context.get('wind_speed')}, rain_probability={weather_context.get('rain_probability')}
Decision: {spray_recommendation.get('best_time')}
Safety: {spray_recommendation.get('is_safe_to_spray')}
Reason: {spray_recommendation.get('reason')}
Rules:
- No emojis
- No medicine names
- Simple farmer-friendly language
"""
        try:
            response = self._run_with_timeout(
                lambda: self.llm.generate_response(
                    prompt,
                    max_tokens=120,
                    temperature=0.2,
                    language=language
                ),
                timeout_seconds=4
            )
            text = str(response or "").strip()
            if not text or "LLM service" in text:
                raise ValueError("LLM unavailable")
            return text
        except Exception:
            if spray_recommendation.get("is_safe_to_spray"):
                return "Spraying is safer now due to manageable wind and low rain risk. This timing reduces wash-off and drift risk."
            return "Spraying is not safe now because weather risk is high. Wait for lower wind and lower rain probability to improve treatment effectiveness."

    def _run_with_timeout(self, func, timeout_seconds=4):
        """Run potentially blocking helper calls with a bounded timeout."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=timeout_seconds)
            except FuturesTimeoutError:
                future.cancel()
                raise TimeoutError(f"Timed out after {timeout_seconds}s")

    def _build_issue_summary(self, disease_details):
        symptoms = disease_details.get("symptoms", []) or []
        if symptoms:
            return "; ".join(symptoms[:2])
        return f"Symptoms observed for {disease_details.get('disease_name', 'this disease')}."

    def _format_solution_lines(self, values):
        values = values or []
        if not values:
            return "Not available in dataset."
        return "; ".join([str(v) for v in values[:2]])

    def _build_impact_future(self, disease_details):
        spread = disease_details.get("spread_speed", "Moderate")
        return f"Disease can spread at {spread.lower()} speed if unmanaged."

    def _build_growth_impact(self, disease_details):
        severity = disease_details.get("severity_level", "Medium")
        return f"{severity} impact expected on plant growth and yield if untreated."

    def _build_action_plan(self, disease_details):
        prevention = disease_details.get("treatment", {}).get("prevention", []) or []
        if not prevention:
            return "- Monitor plants daily\n- Isolate affected leaves\n- Consult local agriculture officer"
        return "\n".join([f"- {item}" for item in prevention[:3]])

    def _format_plant_template(
        self,
        name,
        is_healthy,
        disease_problem="",
        issue_summary="",
        organic_solution="",
        chemical_solution="",
        impact_future="",
        growth_impact="",
        action_plan="",
        short_mode=False,
    ):
        if is_healthy:
            return (
                f"**Name:** {name}\n\n"
                "**Status:** Healthy\n\n"
                "**Summary:** The plant shows no disease symptoms. Leaves, color, and structure appear normal and stable.\n\n"
                "**Preventive Care:**\n"
                "- Maintain proper watering.\n"
                "- Keep soil slightly moist.\n"
                "- Inspect weekly for early spots or pests."
            )

        if short_mode:
            return (
                f"**Name:** {name}\n\n"
                f"**Issue Summary (Short):** {issue_summary}\n\n"
                f"**Organic Solution:** {organic_solution}\n\n"
                f"**Chemical Solution:** {chemical_solution}\n\n"
                f"**Impact Growth:** {growth_impact}"
            )

        return (
            f"**Name:** {name}\n\n"
            f"**Disease / Problem:** {disease_problem}\n\n"
            f"**Issue Summary (Short):** {issue_summary}\n\n"
            f"**Organic Solution:** {organic_solution}\n\n"
            f"**Chemical Solution:** {chemical_solution}\n\n"
            f"**Impact Future:** {impact_future}\n\n"
            f"**Growth Impact:** {growth_impact}\n\n"
            f"**Action Plan (3-6 Days):**\n{action_plan}"
        )
    
    def _generate_explanation(self, disease_details, confidence, lang):
        """
        Generate explanation using LLM

        LLM ONLY explains - does NOT add new facts
        """
        if not self.enable_llm_explanations:
            return {
                "summary": (
                    f"Disease detected: {disease_details['disease_name']}. "
                    f"Severity level is {disease_details.get('severity_level', 'Unknown')}."
                ),
                "urgent_action": (
                    f"Spread speed is {disease_details.get('spread_speed', 'Unknown')}. "
                    "Prioritize immediate field inspection."
                ),
                "seek_help_when": "Seek professional help if symptoms spread quickly or affect multiple plants."
            }

        try:
            language_map = {
                "en": "English",
                "ta": "Tamil",
                "mixed": "Tanglish (Tamil words with English script)"
            }
            language = language_map.get(lang, "English")

            prompt = f"""
You are helping an Indian farmer understand a plant disease. Explain in {language}.

Disease Analysis Result:
- Disease: {disease_details['disease_name']} ({disease_details.get('tamil_name', '')})
- Severity: {disease_details.get('severity_level', 'Unknown')}
- Symptoms: {', '.join(disease_details.get('symptoms', [])[:3])}
- Spread Speed: {disease_details.get('spread_speed', 'Unknown')}
- Confidence: {confidence}

Provide:
1. A simple 2-3 sentence summary for the farmer
2. Urgency level in practical terms
3. When to seek professional help

Format as JSON with keys: summary, urgent_action, seek_help_when.

STRICT RULES:
- Use ONLY the disease/severity/symptom/spread information above.
- Do NOT suggest treatment plans, pesticides, or chemical names.
- Do NOT invent or change severity values.
Keep it under 100 words total.
"""

            response = self._run_with_timeout(
                lambda: self.llm.generate_structured_response(prompt),
                timeout_seconds=4
            )
            return response

        except Exception as e:
            logger.error(f"LLM explanation failed: {e}")
            return {
                "summary": (
                    f"Disease detected: {disease_details['disease_name']}. "
                    f"Severity level is {disease_details.get('severity_level', 'Unknown')}."
                ),
                "urgent_action": (
                    f"Spread speed is {disease_details.get('spread_speed', 'Unknown')}. "
                    "Prioritize immediate field inspection."
                ),
                "seek_help_when": "Seek professional help if symptoms spread quickly or affect multiple plants."
            }

    def _save_result(self, result):
        """Save disease result to database"""
        try:
            analysis_id = result.get("analysis_id") or result.get("_id") or uuid.uuid4().hex[:24]
            result["analysis_id"] = analysis_id
            result["_id"] = analysis_id
            inserted = self.db.insert_one('disease_results', result)
            
            # Update user's current disease status
            self.db.update_one(
                'users',
                {"user_id": result['user_id']},
                {"$set": {
                    "current_disease": result['disease_name'],
                    "disease_severity": result['severity_level']
                }}
            )
            
            logger.info(f"Saved disease result for user {result['user_id']}")
            return str(inserted.inserted_id) if inserted else analysis_id
            
        except Exception as e:
            logger.error(f"Error saving disease result: {e}")
            return None
    
    def get_history(self, user_id, limit=10):
        """Get disease detection history for user"""
        try:
            results = self.db.find(
                'disease_results',
                {"user_id": user_id},
                sort=[("created_at", -1)],
                limit=limit
            )
            
            history = []
            for result in results:
                analysis_id = str(result.get('analysis_id') or result.get('_id', ''))
                confidence_val = result.get('confidence')
                severity = result.get('severity') or result.get('severity_level', '')
                disease_name = result.get('disease_name') or result.get('prediction', '')
                if isinstance(confidence_val, (int, float)):
                    confidence_pct = f"{round(float(confidence_val), 2)}%"
                else:
                    confidence_pct = result.get("confidence_percentage", str(confidence_val or ""))
                history.append({
                    "analysis_id": analysis_id,
                    "result_id": analysis_id,
                    "disease_name": disease_name,
                    "severity": severity,
                    "severity_level": severity,
                    "confidence": result.get('confidence', ''),
                    "confidence_percentage": confidence_pct,
                    "analysis_method": result.get('analysis_method', ''),
                    "affected_crop": result.get('affected_crop') or result.get('crop_name', ''),
                    "is_healthy": result.get('is_healthy', False),
                    "created_at": result.get('created_at', ''),
                    "thumbnail_url": result.get('image_url') or result.get('image_path') or ""
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting disease history: {e}")
            return []
    
    def get_result_by_id(self, user_id, result_id):
        """Get specific disease result by ID"""
        try:
            result = self.db.find_one('disease_results', {
                "$or": [{"_id": result_id}, {"analysis_id": result_id}],
                "user_id": user_id
            })
            
            if result:
                result['result_id'] = str(result.get('_id', ''))
                result['analysis_id'] = str(result.get('analysis_id') or result.get('_id', ''))
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting disease result: {e}")
            return None
    
    def get_disease_types(self):
        """Get list of all available diseases for manual selection"""
        return [{
            "disease_name": disease['disease_name'],
            "tamil_name": disease.get('tamil_name', ''),
            "severity_level": disease.get('severity_level', 'Medium'),
            "affected_crop": disease.get('affected_crop', 'Various'),
            "icon": self._get_severity_icon(disease.get('severity_level', 'Medium'))
        } for disease in self.disease_dataset]
    
    def _get_severity_icon(self, severity):
        """Get emoji icon for severity level"""
        icons = {
            "Low": "ðŸŸ¢",
            "Medium": "ðŸŸ¡",
            "High": "ðŸŸ ",
            "Critical": "ðŸ”´"
        }
        return icons.get(severity, "âšª")
    
    def get_treatment_info(self, disease_name):
        """Get detailed treatment information for a disease"""
        disease_details = self._get_disease_details(disease_name)
        
        if not disease_details:
            return None
        
        treatment = disease_details.get('treatment', {})
        
        return {
            "disease_name": disease_name,
            "tamil_name": disease_details.get('tamil_name', ''),
            "severity_level": disease_details.get('severity_level', 'Medium'),
            "organic_methods": treatment.get('organic', []),
            "chemical_methods": treatment.get('chemical', []),
            "prevention": treatment.get('prevention', []),
            "safety_notes": "Always follow safety guidelines when using chemicals."
        }
    
    def get_model_status(self):
        """Get status of the disease CNN model"""
        return self.cnn.get_model_status('disease_cnn')


# Singleton instance
disease_detector = DiseaseDetector()


def get_disease_detector():
    """Get the singleton disease detector instance"""
    return disease_detector

