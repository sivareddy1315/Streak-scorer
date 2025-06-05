from datetime import datetime, timedelta, timezone, date as DateObject
from typing import Dict, Any, List, Tuple, Optional
from app.core.config import AppConfig
from app.models.streaks_models import StreakInfo

try:
    from app.ai.validator import ContentValidator
except ImportError: 
    class ContentValidator: 
        _model_pipeline = True 
        @staticmethod
        def validate_content(txt: str) -> tuple[bool, str, float | None]:
            logger.warning("Dummy ContentValidator used in streak_logic. AI validation effectively skipped/passed.")
            return True, "Dummy AI Validation (Skipped/Passed)", 1.0 
import logging

logger = logging.getLogger(__name__)

user_streaks_db: Dict[str, Dict[str, Dict[str, Any]]] = {}

def get_utc_date(dt: datetime) -> DateObject:
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()

def calculate_strict_deadline_for_next_day_action(action_date_of_current_valid_streak_event: DateObject) -> datetime:
    reset_hour = AppConfig.get("daily_reset_hour_utc", 0)
    buffer_seconds = AppConfig.get("next_deadline_buffer_seconds", -1)
    logger.debug(f"Calculating deadline based on current valid streak event date: {action_date_of_current_valid_streak_event}")
    deadline_calculation_base_day_start = datetime(
        action_date_of_current_valid_streak_event.year, 
        action_date_of_current_valid_streak_event.month, 
        action_date_of_current_valid_streak_event.day,
        reset_hour, 0, 0, tzinfo=timezone.utc
    ) + timedelta(days=2) 
    calculated_deadline = deadline_calculation_base_day_start + timedelta(seconds=buffer_seconds)
    logger.debug(f"Deadline base (start of day after next): {deadline_calculation_base_day_start}, Calculated strict deadline: {calculated_deadline}")
    return calculated_deadline

def get_streak_tier_name(current_streak_length: int) -> str:
    tiers_config = AppConfig.get("streak_tiers", [])
    calculated_tier = tiers_config[0]["name"] if tiers_config and isinstance(tiers_config, list) and len(tiers_config) > 0 and isinstance(tiers_config[0], dict) and "name" in tiers_config[0] else "none"
    for tier_details in sorted(tiers_config, key=lambda x: x.get("min_streak", 0), reverse=True):
        if current_streak_length >= tier_details.get("min_streak", 0):
            calculated_tier = tier_details.get("name", "none")
            break
    return calculated_tier

class StreakCalculatorService:
    def _validate_action_metadata(self, action_type: str, metadata: Dict[str, Any], action_config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        validators = action_config.get("validators", {})
        if action_type == "quiz":
            min_score = validators.get("min_score")
            if min_score is not None and metadata.get("score", -1) < min_score:
                return False, f"Quiz score {metadata.get('score', 'N/A')} is below minimum {min_score}."
            max_time = validators.get("max_time_taken_sec")
            if max_time is not None and metadata.get("time_taken_sec", float('inf')) > max_time:
                return False, f"Quiz time {metadata.get('time_taken_sec', 'N/A')}s exceeds maximum {max_time}s."
        elif action_type == "help_post":
            min_wc = validators.get("min_word_count")
            if min_wc is not None and metadata.get("word_count", 0) < min_wc:
                return False, f"Help post word count {metadata.get('word_count', 0)} is below minimum {min_wc}."
        return True, None

    def process_user_actions(self, user_id: str, event_datetime_utc: datetime, actions_payload: List[Dict[str, Any]]) -> Dict[str, StreakInfo]:
        logger.info(f"Processing actions for user '{user_id}' with event_datetime_utc: {event_datetime_utc}")
        if user_id not in user_streaks_db: user_streaks_db[user_id] = {}
        
        user_s_data = user_streaks_db[user_id]
        output_s_info: Dict[str, StreakInfo] = {}
        current_event_date = get_utc_date(event_datetime_utc) 
        logger.debug(f"Current event date (UTC date part): {current_event_date}") 
        
        processed_action_types_in_req = set()

        for action_data_item in actions_payload:
            action_type = action_data_item.get("type")
            metadata = action_data_item.get("metadata", {})
            logger.debug(f"Processing action: Type='{action_type}'")
            processed_action_types_in_req.add(action_type)

            action_cfg = AppConfig.get(f"activity_types.{action_type}")
            if not action_cfg or not action_cfg.get("enabled"):
                logger.warning(f"Action type '{action_type}' not configured/enabled. Skipping.")
                continue

            last_s_info = user_s_data.get(action_type, {})
            current_s_val_db = last_s_info.get("current_streak", 0)
            last_event_d_db = last_s_info.get("last_event_date", None) 
            status_db = last_s_info.get("status", "none")

            logger.debug(f"[{action_type}] DB State before: S={current_s_val_db}, LastDate={last_event_d_db}, Status={status_db}")

            is_content_valid, validation_reason = self._validate_action_metadata(action_type, metadata, action_cfg)
            if is_content_valid and action_type == "help_post" and action_cfg.get("validators", {}).get("ai_validation_enabled"):
                if ContentValidator._model_pipeline is None: 
                    try: 
                        logger.warning(f"[{action_type}] ContentValidator model not loaded. Attempting load for action.")
                        ContentValidator.load_model()
                    except Exception as e_load: 
                        logger.error(f"[{action_type}] CRITICAL: Failed to load ContentValidator model: {e_load}. AI validation skipped.")
                        is_content_valid, validation_reason = False, "AI model unavailable during processing."
                if ContentValidator._model_pipeline is not None: 
                    is_content_valid, validation_reason, _ = ContentValidator.validate_content(metadata.get("content", ""))
            
            logger.debug(f"[{action_type}] Content validation passed: {is_content_valid}, Reason: {validation_reason}")

            output_current_streak = current_s_val_db
            output_status = status_db if status_db != "none" else "active" 
            output_next_dl = None
            output_validated = is_content_valid
            output_rejection_reason = None if is_content_valid else validation_reason
            date_this_action_counts_for = current_event_date 

            if not is_content_valid:
                logger.info(f"[{action_type}] Action is invalid. Reason: {validation_reason}")
                if last_event_d_db and current_s_val_db > 0 : 
                    strict_dl_old = calculate_strict_deadline_for_next_day_action(last_event_d_db)
                    effective_dl_old = strict_dl_old + timedelta(hours=AppConfig.get("grace_period_hours", 0))
                    if event_datetime_utc > effective_dl_old: 
                        logger.info(f"[{action_type}] Previous streak ({current_s_val_db} days ending {last_event_d_db}) is now LOST.")
                        output_current_streak, output_status, date_this_action_counts_for = 0, "lost", None
                    else: 
                        output_next_dl = strict_dl_old 
                        output_status = "active" 
                        date_this_action_counts_for = last_event_d_db 
                else: 
                    output_current_streak, output_status, date_this_action_counts_for = 0, "none", None
            
            else: # Action IS VALID
                logger.info(f"[{action_type}] Action is valid. Applying streak logic.")
                if last_event_d_db is None: 
                    logger.debug(f"[{action_type}] First valid action.")
                    output_current_streak, output_status = 1, "active"
                    date_this_action_counts_for = current_event_date
                elif current_event_date == last_event_d_db: 
                    logger.debug(f"[{action_type}] Same day valid action. Streak ({output_current_streak}) and last_event_date ({last_event_d_db}) do not change.")
                    output_status = "active"
                    date_this_action_counts_for = last_event_d_db 
                else: 
                    expected_day_to_continue_streak = last_event_d_db + timedelta(days=1)
                    strict_dl_for_expected_day = calculate_strict_deadline_for_next_day_action(last_event_d_db)
                    effective_dl_for_expected_day = strict_dl_for_expected_day + timedelta(hours=AppConfig.get("grace_period_hours", 0))

                    logger.info(f"DEBUG_GRACE [{action_type}]: last_event_d_db={last_event_d_db}")
                    logger.info(f"DEBUG_GRACE [{action_type}]: current_event_date={current_event_date}")
                    logger.info(f"DEBUG_GRACE [{action_type}]: event_datetime_utc={event_datetime_utc.isoformat()}")
                    logger.info(f"DEBUG_GRACE [{action_type}]: expected_day_to_continue_streak={expected_day_to_continue_streak}")
                    logger.info(f"DEBUG_GRACE [{action_type}]: strict_dl_for_expected_day={strict_dl_for_expected_day.isoformat()}")
                    logger.info(f"DEBUG_GRACE [{action_type}]: effective_dl_for_expected_day={effective_dl_for_expected_day.isoformat()}")
                    
                    condition_met = event_datetime_utc <= effective_dl_for_expected_day
                    logger.info(f"DEBUG_GRACE [{action_type}]: Condition check: event_datetime_utc <= effective_dl_for_expected_day is {condition_met}")
                    
                    if condition_met: 
                        output_current_streak = current_s_val_db + 1
                        date_this_action_counts_for = expected_day_to_continue_streak 
                        logger.debug(f"[{action_type}] Streak continued. New streak: {output_current_streak}. Effective date: {date_this_action_counts_for}")
                    else: 
                        logger.info(f"[{action_type}] Missed effective deadline for day {expected_day_to_continue_streak}. Streak broken.")
                        output_current_streak = 1 
                        date_this_action_counts_for = current_event_date 
                output_status = "active"
            
            user_s_data[action_type] = {
                "current_streak": output_current_streak,
                "last_event_date": date_this_action_counts_for if output_status not in ["lost", "none"] else None,
                "status": output_status
            }
            logger.debug(f"[{action_type}] DB state AFTER this action: {user_s_data[action_type]}")

            if output_status == "active" and output_current_streak > 0 and date_this_action_counts_for is not None:
                output_next_dl = calculate_strict_deadline_for_next_day_action(date_this_action_counts_for)
            
            output_s_info[action_type] = StreakInfo(
                current_streak=output_current_streak, status=output_status, tier=get_streak_tier_name(output_current_streak),
                next_deadline_utc=output_next_dl, validated=output_validated, rejection_reason=output_rejection_reason)

        all_user_action_types = set(user_s_data.keys())
        for act_type_to_re_eval in all_user_action_types - processed_action_types_in_req:
            db_entry = user_s_data[act_type_to_re_eval]
            c_s, l_e_d, stat = db_entry.get("current_streak",0), db_entry.get("last_event_date"), db_entry.get("status","none")
            n_d_o_re_eval = None
            logger.debug(f"Re-evaluating '{act_type_to_re_eval}': DB state: S={c_s}, Date={l_e_d}, Status={stat}. Current Request EventTime={event_datetime_utc}")

            if l_e_d and c_s > 0 and stat == "active": 
                strict_dl_for_continuation = calculate_strict_deadline_for_next_day_action(l_e_d)
                effective_dl_for_continuation = strict_dl_for_continuation + timedelta(hours=AppConfig.get("grace_period_hours", 0))
                logger.debug(f"[{act_type_to_re_eval}] Re-eval StrictDL={strict_dl_for_continuation}, EffectiveDL={effective_dl_for_continuation}")
                if event_datetime_utc > effective_dl_for_continuation: 
                    logger.info(f"[{act_type_to_re_eval}] Streak LOST (re-evaluation).")
                    db_entry["current_streak"], db_entry["status"], db_entry["last_event_date"] = 0, "lost", None
                else: 
                    n_d_o_re_eval = strict_dl_for_continuation 
            elif c_s == 0 and stat != "lost": 
                db_entry["status"] = "none"
            
            output_s_info[act_type_to_re_eval] = StreakInfo(
                current_streak=db_entry["current_streak"], 
                status=db_entry["status"], 
                tier=get_streak_tier_name(db_entry["current_streak"]),
                next_deadline_utc=n_d_o_re_eval 
            )
        logger.info(f"Final processed streaks for user '{user_id}': {output_s_info}")
        return output_s_info