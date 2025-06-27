# This program was developed with help from Cursor AI and Google AI Studio.
import logging
from fastapi import FastAPI, HTTPException, Request 
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager 

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__) 

try:
    from app.core.config import AppConfig
    from app.models.streaks_models import StreakUpdateRequest, StreakUpdateResponse 
    from app.services.streak_logic import StreakCalculatorService # Assumes this expects uid, event_dt_utc, actions_load
    from app.ai.validator import ContentValidator
except ImportError as e:
    logger.error(f"CRITICAL IMPORT ERROR in main.py: {e}. Check PYTHONPATH and file structure.", exc_info=True)
    raise 

@asynccontextmanager
async def lifespan(app_instance: FastAPI): 
    logger.info("Application startup sequence initiated (lifespan)...")
    try:
        AppConfig.load_config() 
        logger.info(f"Configuration loaded/verified during startup. Service version: {AppConfig.get('service_version')}")
        help_post_config = AppConfig.get("activity_types.help_post", {})
        if help_post_config.get("enabled") and \
           help_post_config.get("validators", {}).get("ai_validation_enabled"):
            logger.info("Attempting to load AI model for help_post validation...")
            ContentValidator.load_model() 
            logger.info("AI Model for help_post loaded successfully.")
        else:
            logger.info("AI model for help_post is not configured or not enabled for AI validation in config.")
        app_instance.state.streak_service = StreakCalculatorService() 
        logger.info("StreakCalculatorService initialized and stored in app.state.streak_service.")
        logger.info("Application startup complete (lifespan).")
    except FileNotFoundError as e:
        logger.error(f"CRITICAL STARTUP ERROR (lifespan) - File Not Found: {e}", exc_info=True)
        raise RuntimeError(f"Startup failed (lifespan) due to missing file: {e}") from e
    except Exception as e:
        logger.error(f"CRITICAL STARTUP ERROR (lifespan): {e}", exc_info=True)
        raise RuntimeError(f"General startup failure (lifespan): {e}") from e
    yield 
    logger.info("Application shutdown sequence initiated (lifespan)...")
    if hasattr(app_instance.state, 'streak_service'): del app_instance.state.streak_service
    logger.info("Application shutdown complete (lifespan).")

try:
    if not AppConfig._loaded: AppConfig.load_config()
    SERVICE_VERSION_FOR_APP_DEF = AppConfig.get("service_version", "0.0.0-config-error")
except Exception as e:
    logger.error(f"Failed to load AppConfig or get service_version for FastAPI app definition: {e}. Using default.")
    SERVICE_VERSION_FOR_APP_DEF = "0.0.0-critical-config-error"

app = FastAPI(
    title="Streak Scoring Microservice",
    description="Tracks and validates user engagement streaks.",
    version=SERVICE_VERSION_FOR_APP_DEF,
    openapi_tags=[
        {"name": "General", "description": "General service information and status"},
        {"name": "Streaks", "description": "Operations related to user streaks."},
    ],
    lifespan=lifespan 
)

@app.get("/", tags=["General"], response_class=HTMLResponse)
async def read_root_html():
    logger.info("--- ENTERING read_root_html ---")
    try:
        current_service_version = AppConfig.get("service_version", "N/A - Error loading version") 
        logger.info(f"read_root_html: Fetched service version: {current_service_version}")
        html_content = f"""
        <html><head><title>Streak Scoring Microservice</title><style>body{{font-family:Arial,sans-serif;margin:40px;line-height:1.6;background-color:#f8f9fa;color:#212529;}}.container{{max-width:800px;margin:auto;padding:30px;border:1px solid #dee2e6;border-radius:8px;background-color:#fff;box-shadow:0 4px 8px rgba(0,0,0,0.1);}}h1{{color:#007bff;border-bottom:2px solid #007bff;padding-bottom:10px;}}ul{{list-style-type:none;padding-left:0;}}li{{margin-bottom:8px;background-color:#e9ecef;padding:10px;border-radius:4px;}}a{{color:#0056b3;text-decoration:none;font-weight:bold;}}a:hover{{text-decoration:underline;color:#003875;}}.footer-note{{font-size:0.9em;color:#7f8c8d;margin-top:30px;}}</style></head>
        <body><div class="container"><h1>Welcome to the Streak Scoring Microservice!</h1><p>This API tracks and validates user engagement streaks.</p><h2>Explore:</h2><ul>
        <li><a href="/docs">API Documentation (Swagger UI)</a></li><li><a href="/redoc">API Documentation (ReDoc)</a></li>
        <li><a href="/health">Health Check</a></li><li><a href="/version">Version Info</a></li></ul>
        <p class="footer-note">Service Version: {current_service_version}</p></div></body></html>
        """
        logger.info("--- EXITING read_root_html successfully ---")
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        logger.error(f"--- ERROR in read_root_html: {e} ---", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating root page: {str(e)}")

@app.post("/streaks/update", response_model=StreakUpdateResponse, tags=["Streaks"])
async def update_user_streaks_endpoint(request_payload: StreakUpdateRequest, http_request: Request): 
    if not hasattr(http_request.app.state, 'streak_service'):
        logger.error("CRITICAL: streak_service not found in app.state. Lifespan startup might have failed.")
        raise HTTPException(status_code=503, detail="Service core component not initialized.")
        
    streak_service = http_request.app.state.streak_service
    
    if not isinstance(streak_service, StreakCalculatorService): 
        logger.error(f"CRITICAL: app.state.streak_service is not a StreakCalculatorService instance. Type: {type(streak_service)}")
        raise HTTPException(status_code=503, detail="Service component type mismatch. Check server startup logs.")
    try:
        logger.info(f"Processing /streaks/update for user_id: {request_payload.user_id}")
        actions_list_of_dicts = [action.model_dump() for action in request_payload.actions]
        
        # +++ THIS IS THE CORRECTED CALL +++
        streaks_summary = streak_service.process_user_actions(
            uid=request_payload.user_id,                 # Changed to 'uid'
            event_dt_utc=request_payload.date_utc,      # Changed to 'event_dt_utc'
            actions_load=actions_list_of_dicts      # Changed to 'actions_load'
        )
        # +++++++++++++++++++++++++++++++++++++
        
        logger.info(f"Successfully processed /streaks/update for user_id: {request_payload.user_id}")
        return StreakUpdateResponse(user_id=request_payload.user_id, streaks=streaks_summary)
    except Exception as e:
        logger.error(f"Error during /streaks/update for user {request_payload.user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during streak update.")

@app.get("/health", tags=["Status"])
async def health_check_endpoint():
    logger.debug("Health check called.")
    return {"status": "ok"}

@app.get("/version", tags=["Status"])
async def get_version_info_endpoint():
    logger.debug("Version endpoint called.")
    try:
        if not AppConfig._config_data and not AppConfig._loaded : 
             logger.warning("AppConfig might not have been loaded by lifespan, attempting explicit load in /version.")
             AppConfig.load_config() 
        elif not AppConfig._config_data and AppConfig._loaded: 
             logger.error("/version endpoint: AppConfig data is empty, previous load attempt likely failed.")

        service_api_version = AppConfig.get("service_version", "N/A - Config Error") 
        ai_model_versions_config = AppConfig.get("model_versions", {}) 

        if service_api_version == "N/A - Config Error": 
            logger.error("/version endpoint: service_version not found in AppConfig or load failed.")
        if not ai_model_versions_config : 
            logger.warning("/version endpoint: model_versions missing or empty in AppConfig.")
         
        return {
            "service_name": "Streak Scoring Microservice",
            "service_api_version": service_api_version, 
            "ai_model_versions": ai_model_versions_config 
        }
    except Exception as e: 
        logger.error(f"Error in /version endpoint while accessing AppConfig: {e}", exc_info=True)
        return { 
            "service_name": "Streak Scoring Microservice",
            "service_api_version": "N/A - Error Retrieving Version",
            "ai_model_versions": {},
            "error_details": f"Failed to retrieve version information: {str(e)}"
        }