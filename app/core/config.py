import json
import os
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class AppConfig:
    _config_data: Dict[str, Any] = {}
    _config_path: Optional[str] = None
    _loaded: bool = False # Flag to see if it has attempted loading

    @classmethod
    def load_config(cls, config_file_path: Optional[str] = None):
        # Prevent re-loading if already loaded from the same path,
        # but allow explicit re-load if a new path is given (useful for tests).
        if cls._loaded and (config_file_path is None or config_file_path == cls._config_path):
            logger.debug(f"Config already loaded from {cls._config_path}. Skipping reload.")
            return

        if config_file_path is None:
            if cls._config_path is None: # If no path ever set, determine default
                current_script_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.abspath(os.path.join(current_script_dir, '..', '..'))
                cls._config_path = os.path.join(project_root, 'config.json')
            # Use the stored cls._config_path if config_file_path is None but cls._config_path was set before
            actual_config_path = cls._config_path
        else: # A specific path is provided
            cls._config_path = config_file_path
            actual_config_path = config_file_path
        
        logger.info(f"Attempting to load configuration from: {actual_config_path}")
        if not os.path.exists(actual_config_path):
            logger.error(f"CRITICAL: Configuration file not found at {actual_config_path}")
            # Set loaded to true even on failure to prevent reload loops if default path is wrong
            cls._loaded = True 
            raise FileNotFoundError(f"Configuration file not found: {actual_config_path}")

        try:
            with open(actual_config_path, 'r') as f:
                cls._config_data = json.load(f)
            cls._loaded = True # Mark as loaded successfully
            logger.info(f"Configuration loaded successfully from {actual_config_path}")
        except json.JSONDecodeError as e:
            cls._loaded = True # Mark attempt even on failure
            logger.error(f"CRITICAL: Error decoding JSON from {actual_config_path}: {e}")
            raise ValueError(f"Error decoding JSON from {actual_config_path}: {e}")
        except Exception as e:
            cls._loaded = True # Mark attempt even on failure
            logger.error(f"CRITICAL: Could not load config from {actual_config_path}: {e}", exc_info=True)
            raise RuntimeError(f"Could not load config from {actual_config_path}: {e}")

    @classmethod
    def get(cls, key_path: str, default_value: Any = None) -> Any:
        if not cls._loaded: # If never attempted to load
            cls.load_config() 
        
        # If loading failed and _config_data is empty, subsequent gets will return default
        if not cls._config_data and cls._loaded: # Loaded (or attempted) but data is empty
             logger.warning(f"AppConfig.get('{key_path}'): Config data is empty (load might have failed). Returning default.")
             return default_value

        keys = key_path.split('.')
        current_level_data = cls._config_data
        for key_part in keys:
            if isinstance(current_level_data, dict) and key_part in current_level_data:
                current_level_data = current_level_data[key_part]
            else:
                # logger.debug(f"Key part '{key_part}' not found in path '{key_path}'. Returning default: {default_value}")
                return default_value
        return current_level_data

# Attempt to load config when this module is imported.
# This makes it available early. Errors during this load will be raised.
if not AppConfig._loaded:
    try:
        AppConfig.load_config()
    except Exception as e:
        # Log error but allow module to be imported so app can potentially handle missing config.
        # However, FastAPI app instantiation might fail if it relies on AppConfig.get for version.
        logger.error(f"Initial AppConfig load failed during module import: {e}. "
                     "The application might not start correctly if config is essential at FastAPI app definition.")
        # Depending on how critical config is at app definition time, you might re-raise here.
        # For now, let it pass, startup_event in main.py will try again / raise.