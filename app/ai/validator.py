import joblib
import os
import logging
import nltk 
from nltk.corpus import stopwords 
import re 
from typing import Tuple, Optional # <<<--- IMPORT Optional

from app.core.config import AppConfig 

logger = logging.getLogger(__name__)

# --- Preprocessing Logic (Inlined - Keep Identical in trainer.py) ---
def _get_english_stopwords():
    try:
        sw = set(stopwords.words('english'))
    except LookupError: 
        try: nltk.data.find('corpora/stopwords.zip')
        except nltk.downloader.DownloadError: logger.warning("[VALIDATOR] NLTK stopwords pkg not found. Downloading."); nltk.download('stopwords', quiet=True)
        except Exception as e: logger.error(f"[VALIDATOR] NLTK stopwords path issue: {e}"); raise
        sw = set(stopwords.words('english')) 
    return sw

ENGLISH_STOPWORDS_SET = _get_english_stopwords()

def common_preprocess_text(text: str) -> str: 
    if not isinstance(text, str): return ""
    text = text.lower()
    text = re.sub(r'[^\w\s\.\(\)\+\-\*/\=\<\>\%]', '', text)
    words = text.split()
    processed_words = [w for w in words if w not in ENGLISH_STOPWORDS_SET and len(w) > 0]
    return " ".join(processed_words)
# --- End of Inlined Preprocessing Logic ---

class ContentValidator:
    _model_pipeline = None; _loaded_model_version = None; _model_base_path = None

    @classmethod
    def _initialize_paths(cls):
        if cls._model_base_path is None:
            cls._model_base_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')), 'data', 'trained_models')

    @classmethod
    def load_model(cls):
        # ... (load_model logic remains the same as the last complete version)
        cls._initialize_paths()
        try: AppConfig.get("service_version") 
        except Exception: logger.error("AppConfig not accessible in ContentValidator.load_model. Using defaults.")
        
        model_ver = AppConfig.get("model_versions.help_post_classifier", "1.0.0")
        if cls._model_pipeline and cls._loaded_model_version == model_ver: logger.info(f"AI Model v{model_ver} already loaded."); return

        model_path = os.path.join(cls._model_base_path, f'help_post_classifier_v{model_ver}.pkl')
        if not os.path.exists(model_path): raise FileNotFoundError(f"AI Model not found: {model_path}")
        try:
            cls._model_pipeline = joblib.load(model_path); cls._loaded_model_version = model_ver
            logger.info(f"Help post model v{model_ver} loaded from {model_path}")
        except Exception as e: logger.error(f"Error loading AI model: {e}", exc_info=True); cls._model_pipeline = None; raise


    @classmethod
    def validate_content(cls, content_text: str) -> Tuple[bool, str, Optional[float]]: # <<<--- CHANGED HERE
        if not cls._model_pipeline: 
            logger.error("AI model pipeline is not loaded. Cannot validate content.")
            return False, "AI model not available for validation.", None

        original_text_for_log = content_text[:200] 
        processed_text = common_preprocess_text(content_text) 
        
        logger.info(f"--- AI VALIDATION DIAGNOSTICS (validator.py) ---")
        logger.info(f"Original Input Snippet: '{original_text_for_log}...'")
        logger.info(f"Processed Text for Model: '{processed_text[:200]}...'")

        if not processed_text.strip():
            logger.info("Content became empty after preprocessing.")
            logger.info(f"--- END AI VALIDATION DIAGNOSTICS ---")
            return False, "Content is empty or contains only stopwords/punctuation after processing.", None

        try:
            prediction_result = cls._model_pipeline.predict([processed_text])[0] 
            probabilities = cls._model_pipeline.predict_proba([processed_text])[0] 
            
            model_classes = list(cls._model_pipeline.classes_) 
            class_1_index = -1
            try:
                class_1_index = model_classes.index(1) 
            except ValueError:
                 logger.error(f"Critical: Class '1' (good) not found in model's learned classes: {model_classes}")
                 logger.info(f"--- END AI VALIDATION DIAGNOSTICS ---")
                 return False, "AI model configuration error (class labels).", None

            confidence_for_class_1 = float(probabilities[class_1_index]) 
            
            logger.info(f"Model's Learned Classes: {model_classes}")
            logger.info(f"Raw Prediction (0 or 1): {prediction_result}")
            logger.info(f"Probabilities array (corresponds to classes {model_classes}): {probabilities}")
            logger.info(f"Calculated Probability for Class 1 (Good): {confidence_for_class_1:.4f}")
            
            is_final_valid_prediction = bool(prediction_result == 1)

            logger.info(f"Final Decision (is_valid_prediction): {is_final_valid_prediction}")
            logger.info(f"--- END AI VALIDATION DIAGNOSTICS ---")

            if is_final_valid_prediction:
                return True, f"Content classified as valid by AI (Prob_Good: {confidence_for_class_1:.2f})", confidence_for_class_1
            else:
                rejection_msg = f"Content classified as low quality/irrelevant by AI (Prob_Good: {confidence_for_class_1:.2f})"
                return False, rejection_msg, confidence_for_class_1
        except Exception as e: 
            logger.error(f"ERROR during AI content validation: {e}", exc_info=True)
            logger.info(f"--- END AI VALIDATION DIAGNOSTICS (ERROR) ---")
            return False, "An error occurred during AI validation.", None