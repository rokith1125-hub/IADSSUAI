"""
CNN Service - PRODUCTION READY
NO fake data, NO random predictions, NO fallbacks

If a model is unavailable:
→ Return CLEAR error message
→ NEVER simulate results
"""

import numpy as np
import json
import os
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# TensorFlow availability
TF_AVAILABLE = False
tf = None
keras = None
TF_IMPORT_ERROR = None

try:
    import tensorflow as tf
    # TensorFlow 2.16+ moved keras to separate package
    try:
        from tensorflow import keras
    except ImportError:
        # Fallback for older TensorFlow versions
        import tensorflow.keras as keras
    TF_AVAILABLE = True
    logger.info("✅ TensorFlow available for CNN inference")
except Exception as e:
    TF_IMPORT_ERROR = str(e)
    logger.warning(f"TensorFlow unavailable - CNN predictions disabled: {e}")

# PIL for image processing
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False
    logger.warning("⚠️ PIL not installed - image processing unavailable")


class ModelNotAvailableError(Exception):
    """Raised when CNN model is not available"""
    pass


class LabelConfigError(Exception):
    """Raised when CNN label configuration is missing or invalid"""
    pass


class ImageProcessingError(Exception):
    """Raised when image processing fails"""
    pass


class CNNService:
    """
    Production CNN Service
    - NO fallbacks
    - NO fake predictions
    - Clear error messages when models unavailable
    """
    
    def __init__(self):
        # Get models directory
        backend_root = Path(__file__).parent.parent
        self.models_dir = backend_root / 'ai_models'
        
        self.models = {}
        self.model_configs = {}
        
        # Model/config paths with fallback resolution.
        self.model_paths = {
            'soil': self._resolve_asset_path('soil_cnn.h5', category='soil'),
            'disease': self._resolve_asset_path('disease_cnn.h5', category='disease')
        }
        self.config_paths = {
            'soil': self._resolve_asset_path('soil_cnn.json', category='soil'),
            'disease': self._resolve_asset_path('disease_cnn.json', category='disease')
        }

        logger.info(f"Soil model path: {self.model_paths['soil']}")
        logger.info(f"Disease model path: {self.model_paths['disease']}")

    def _resolve_asset_path(self, filename, category=''):
        """
        Resolve model/config path from common locations.
        Prefers existing file; otherwise returns default ai_models/<filename>.
        """
        candidates = [
            self.models_dir / filename,
            self.models_dir / category / filename if category else None,
            self.models_dir / 'soil' / filename,
            self.models_dir / 'disease' / filename,
            self.models_dir / 'cnn' / filename,
            Path.cwd() / 'ai_models' / filename,
            Path.cwd() / filename,
        ]

        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate

        return self.models_dir / filename

    def _normalize_model_name(self, model_name):
        """Support both short keys and explicit model filename prefixes."""
        aliases = {
            'soil_cnn': 'soil',
            'soil': 'soil',
            'disease_cnn': 'disease',
            'disease': 'disease'
        }
        return aliases.get(model_name, model_name)

    def _normalize_labels(self, raw_config):
        """
        Normalize label config into {str(index): str(label)}.

        Supports common formats:
        - {"0": "ClassA", "1": "ClassB"}
        - [{"0": "ClassA", "1": "ClassB"}]
        - ["ClassA", "ClassB"]
        - {"labels": {...}} / {"class_indices": {...}} / {"class_names": [...]}
        """
        if raw_config is None:
            return {}

        config = raw_config

        # Some exports wrap the dict in a single-item list.
        if isinstance(config, list):
            if len(config) == 1 and isinstance(config[0], dict):
                config = config[0]
            else:
                # Assume direct label list.
                return {str(i): str(v) for i, v in enumerate(config)}

        # Common wrapper keys.
        if isinstance(config, dict):
            for key in ("labels", "class_indices", "class_index", "classes", "class_names"):
                if key in config:
                    wrapped = config[key]
                    if isinstance(wrapped, list):
                        return {str(i): str(v) for i, v in enumerate(wrapped)}
                    if isinstance(wrapped, dict):
                        return {str(k): str(v) for k, v in wrapped.items()}

            # Already in direct dict format.
            return {str(k): str(v) for k, v in config.items()}

        return {}

    def _format_soil_class_name(self, class_name):
        """Normalize soil class display text."""
        if not class_name:
            return class_name
        # Apply triple separator replacement first, then generic underscores.
        pretty = str(class_name).replace("___", " - ").replace("_", " ")
        pretty = re.sub(r"\s+", " ", pretty).strip()
        return pretty

    def _format_disease_class_name(self, class_name):
        """Normalize disease class display text."""
        if not class_name:
            return class_name
        pretty = str(class_name).replace("___", " - ").replace("_", " ")
        pretty = re.sub(r"\s+", " ", pretty).strip(" -")
        return pretty

    def _resolve_class_name(self, labels, predicted_idx, default_prefix):
        """Resolve class name robustly from label mapping."""
        if not isinstance(labels, dict) or not labels:
            return f"{default_prefix}_{predicted_idx}"

        # Prefer string key, then integer key fallback.
        if str(predicted_idx) in labels:
            return labels[str(predicted_idx)]
        if predicted_idx in labels:
            return labels[predicted_idx]
        return f"{default_prefix}_{predicted_idx}"

    def _get_model_target_size(self, model_name, default=(224, 224)):
        """Use actual model input shape when available."""
        model = self.load_model(model_name)
        input_shape = getattr(model, "input_shape", None)

        # Multi-input models can return list/tuple of shapes.
        if isinstance(input_shape, (list, tuple)) and input_shape and isinstance(input_shape[0], (list, tuple)):
            input_shape = input_shape[0]

        try:
            height = int(input_shape[1]) if input_shape and input_shape[1] else default[0]
            width = int(input_shape[2]) if input_shape and input_shape[2] else default[1]
            # Basic sanity.
            if height < 32 or width < 32:
                return default
            return (height, width)
        except Exception:
            return default
    
    def is_tensorflow_available(self):
        """Check if TensorFlow is available"""
        return TF_AVAILABLE
    
    def is_model_available(self, model_name):
        """Check if a specific model is available"""
        model_name = self._normalize_model_name(model_name)
        if not TF_AVAILABLE:
            return False
        
        model_path = self.model_paths.get(model_name)
        config_path = self.config_paths.get(model_name)
        if not model_path or not model_path.exists():
            return False
        if not config_path or not config_path.exists():
            return False
        
        # Check file size (valid models are at least 1KB)
        if model_path.stat().st_size < 1000:
            return False

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                labels = self._normalize_labels(json.load(f))
            return bool(labels)
        except Exception:
            return False
    
    def get_model_status(self, model_name):
        """Get detailed status of a model"""
        requested_name = model_name
        model_name = self._normalize_model_name(model_name)
        model_path = self.model_paths.get(model_name)
        config_path = self.config_paths.get(model_name)
        
        status = {
            'model_name': requested_name,
            'tensorflow_available': TF_AVAILABLE,
            'pil_available': PIL_AVAILABLE,
            'model_file_exists': model_path.exists() if model_path else False,
            'config_file_exists': config_path.exists() if config_path else False,
            'available': False,
            'error': None,
            'tensorflow_import_error': TF_IMPORT_ERROR
        }
        
        if not TF_AVAILABLE:
            status['error'] = 'Model unavailable. Please deploy trained model.'
        elif not model_path or not model_path.exists() or model_path.stat().st_size < 1000:
            status['error'] = 'Model unavailable. Please deploy trained model.'
        elif not config_path or not config_path.exists():
            status['error'] = 'Label configuration missing.'
        else:
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    labels = self._normalize_labels(json.load(f))
                if not labels:
                    status['error'] = 'Label configuration missing.'
                else:
                    status['available'] = True
                    status['file_size_kb'] = round(model_path.stat().st_size / 1024, 2)
                    status['labels_count'] = len(labels)
            except Exception:
                status['error'] = 'Label configuration missing.'
        
        return status
    
    def load_model(self, model_name):
        """
        Load CNN model
        
        CRITICAL: Raises ModelNotAvailableError if model cannot be loaded
        NEVER returns None - we either have a model or we fail clearly
        """
        model_name = self._normalize_model_name(model_name)

        # Return cached model if available
        if model_name in self.models:
            return self.models[model_name]
        
        # Check TensorFlow
        if not TF_AVAILABLE:
            raise ModelNotAvailableError(
                "Model unavailable. Please deploy trained model."
            )
        
        # Check PIL
        if not PIL_AVAILABLE:
            raise ModelNotAvailableError(
                "PIL (Pillow) is not installed. "
                "Please install Pillow for image processing: pip install Pillow"
            )
        
        # Get model path
        model_path = self.model_paths.get(model_name)
        if not model_path:
            raise ModelNotAvailableError(
                f"Unknown model: {model_name}. Available models: soil, disease"
            )
        
        # Check model file exists
        if not model_path.exists():
            raise ModelNotAvailableError(
                "Model unavailable. Please deploy trained model."
            )
        
        # Check model file is valid
        if model_path.stat().st_size < 1000:
            raise ModelNotAvailableError(
                "Model unavailable. Please deploy trained model."
            )
        
        # Load the model
        try:
            logger.info(f"Loading model: {model_name} from {model_path}")
            model = tf.keras.models.load_model(str(model_path), compile=False)
            
            # Load config/labels
            config_path = self.config_paths.get(model_name)
            if not config_path or not config_path.exists():
                raise LabelConfigError("Label configuration missing.")
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = self._normalize_labels(json.load(f))
            except Exception as e:
                logger.warning(f"Could not load config for {model_name}: {e}")
                raise LabelConfigError("Label configuration missing.")
            if not config:
                raise LabelConfigError("Label configuration missing.")
            
            # Cache the model
            self.models[model_name] = model
            self.model_configs[model_name] = config
            
            logger.info(f"✅ Model '{model_name}' loaded successfully")
            return model
            
        except LabelConfigError:
            raise ModelNotAvailableError("Label configuration missing.")
        except ModelNotAvailableError:
            raise
        except Exception as e:
            logger.error(f"Failed to load model '{model_name}': {str(e)}")
            raise ModelNotAvailableError(
                "Model unavailable. Please deploy trained model."
            )
    
    def get_labels(self, model_name):
        """Get class labels for a model"""
        model_name = self._normalize_model_name(model_name)
        # Make sure model is loaded
        if model_name not in self.model_configs:
            self.load_model(model_name)

        labels = self._normalize_labels(self.model_configs.get(model_name, {}))
        if not labels:
            raise ModelNotAvailableError("Label configuration missing.")
        return labels
    
    def preprocess_image(self, image_path=None, image_bytes=None, target_size=(224, 224)):
        """
        Preprocess image for CNN input
        
        CRITICAL: Raises ImageProcessingError on failure
        NEVER returns None
        """
        if not PIL_AVAILABLE:
            raise ImageProcessingError(
                "PIL (Pillow) is not installed. "
                "Please install Pillow for image processing."
            )
        
        try:
            import io
            
            # Load image
            if image_bytes:
                img = Image.open(io.BytesIO(image_bytes))
            elif image_path:
                if not os.path.exists(image_path):
                    raise ImageProcessingError(f"Image file not found: {image_path}")
                img = Image.open(image_path)
            else:
                raise ImageProcessingError("Either image_path or image_bytes must be provided")
            
            # Convert to RGB (Step 4 from USER)
            img = img.convert("RGB")
            
            # Resize
            img = img.resize(target_size, Image.Resampling.LANCZOS)
            
            # Convert to numpy array and normalize
            img_array = np.array(img, dtype=np.float32) / 255.0
            
            # Add batch dimension
            img_array = np.expand_dims(img_array, axis=0)
            
            return img_array
            
        except ImageProcessingError:
            raise
        except Exception as e:
            logger.error(f"Image preprocessing failed: {str(e)}")
            raise ImageProcessingError(f"Failed to process image: {str(e)}")
    
    def predict(self, model_name, image_array):
        """
        Make prediction using CNN model
        
        Returns raw predictions array
        
        CRITICAL: Raises ModelNotAvailableError if model unavailable
        """
        model_name = self._normalize_model_name(model_name)
        model = self.load_model(model_name)
        
        try:
            predictions = model.predict(image_array, verbose=0)
            return predictions
        except Exception as e:
            logger.error(f"Prediction failed: {str(e)}")
            raise ModelNotAvailableError(f"Model prediction failed: {str(e)}")
    
    def predict_soil(self, image_path=None, image_bytes=None):
        """
        Predict soil type from image
        
        Returns:
            dict: Contains class_name, confidence, and all_predictions
            
        CRITICAL:
        - Returns ONLY class label + confidence
        - NO explanations, NO suggestions
        - Raises error if model unavailable
        """
        # Preprocess image
        target_size = self._get_model_target_size('soil')
        img_array = self.preprocess_image(
            image_path=image_path,
            image_bytes=image_bytes,
            target_size=target_size
        )
        
        # Get predictions
        predictions = self.predict('soil', img_array)
        
        # Get labels
        labels = self.get_labels('soil')
        
        # Process results
        predicted_idx = int(np.argmax(predictions[0]))
        confidence = float(predictions[0][predicted_idx])
        
        class_name_raw = self._resolve_class_name(labels, predicted_idx, "Soil_Class")
        class_name = self._format_soil_class_name(class_name_raw)
        pretty = self._format_soil_class_name(class_name)

        return {
            'prediction': {
                'class_index': predicted_idx,
                'class_name': pretty,
                'class_name_raw': class_name_raw,
                'confidence': round(confidence * 100, 2),
            },
            'class_index': predicted_idx,
            'class_name': pretty,
            'class_name_raw': class_name_raw,
            'confidence': round(confidence * 100, 2),
            'all_predictions': {
                self._format_soil_class_name(self._resolve_class_name(labels, i, "Class")): round(float(predictions[0][i]) * 100, 2)
                for i in range(len(predictions[0]))
            }
        }
    
    def predict_disease(self, image_path=None, image_bytes=None):
        """
        Predict plant disease from image
        
        Returns:
            dict: Contains class_name, confidence, is_healthy, and all_predictions
            
        CRITICAL:
        - Returns ONLY class label + confidence
        - NO treatment suggestions
        - Raises error if model unavailable
        """
        # Preprocess image
        target_size = self._get_model_target_size('disease')
        img_array = self.preprocess_image(
            image_path=image_path,
            image_bytes=image_bytes,
            target_size=target_size
        )
        
        # Get predictions
        predictions = self.predict('disease', img_array)
        
        # Get labels
        labels = self.get_labels('disease')
        
        # Process results - TOP 3 (Step 1 from USER)
        indices = np.argsort(predictions[0])[-3:][::-1]
        top3_classes = []
        
        for idx in indices:
            idx = int(idx)
            conf = float(predictions[0][idx])
            raw_label = self._resolve_class_name(labels, idx, "Disease_Class")
            pretty_label = self._format_disease_class_name(raw_label)
            top3_classes.append({
                "class": pretty_label,
                "class_raw": raw_label,
                "confidence": round(conf * 100, 2),
                "index": idx
            })

        # Log top predictions (Step 6 from USER)
        logger.info(f"Top 3 Disease predictions: {top3_classes}")

        primary = top3_classes[0]
        class_name = primary["class"]
        class_name_raw = primary["class_raw"]
        confidence = primary["confidence"]
        
        class_name_lower = class_name.lower()
        is_healthy = 'healthy' in class_name_lower or 'normal' in class_name_lower

        return {
            'primary': primary,
            'alternatives': top3_classes[1:],
            'class_index': primary["index"],
            'class_name': class_name,
            'class_name_raw': class_name_raw,
            'confidence': confidence,
            'is_healthy': is_healthy,
            'top_predictions': top3_classes,
            'all_predictions': {
                self._format_disease_class_name(self._resolve_class_name(labels, i, "Class")): round(float(predictions[0][i]) * 100, 2)
                for i in range(len(predictions[0]))
            }
        }


# Singleton instance
cnn_service = CNNService()


def get_cnn_service():
    """Get the singleton CNN service instance"""
    return cnn_service
