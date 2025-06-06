from datetime import datetime, timedelta, timezone, date as DateObject
from typing import Dict, Any, List, Tuple, Optional
from app.core.config import AppConfig
from app.models.streaks_models import StreakInfo
from app.ai.validator import ContentValidator

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

FAILING_TEST_USER_ID_FOR_LOGGING = "user_timeout_tests_report_lost" 

# Initialize ContentValidator
try:
    ContentValidator.load_model()
    logger.info("ContentValidator initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize ContentValidator: {e}")

user_streaks_db: Dict[str, Dict[str, Dict[str, Any]]] = {}

def get_utc_date(dt: datetime) -> DateObject: # Line 30
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date() # Line 31 (Corrected)

def calculate_strict_deadline_for_next_day_action(action_date_event: DateObject) -> datetime:
    reset_hour = AppConfig.get("daily_reset_hour_utc", 0)
    buffer_seconds = AppConfig.get("next_deadline_buffer_seconds", -1)
    logger.debug(f"Calculating deadline based on current valid streak event date: {action_date_event}")
    base_day_start = datetime(
        action_date_event.year, action_date_event.month, action_date_event.day,
        reset_hour, 0, 0, tzinfo=timezone.utc
    ) + timedelta(days=2) 
    deadline = base_day_start + timedelta(seconds=buffer_seconds)
    logger.debug(f"Deadline for action after {action_date_event}: {deadline}")
    return deadline

def get_streak_tier_name(streak_len: int) -> str:
    tiers = AppConfig.get("streak_tiers", [])
    tier_name = tiers[0]["name"] if tiers and isinstance(tiers[0], dict) and "name" in tiers[0] else "none"
    for td in sorted(tiers, key=lambda x: x.get("min_streak", 0), reverse=True):
        if streak_len >= td.get("min_streak", 0):
            tier_name = td.get("name", "none"); break
    return tier_name

class StreakCalculatorService:
    def _validate_action_metadata(self, type: str, meta: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        validators = cfg.get("validators", {})
        if type == "quiz":
            if validators.get("min_score") is not None and meta.get("score", -1) < validators["min_score"]:
                return False, f"Quiz score {meta.get('score', 'N/A')} below min {validators['min_score']}."
            if validators.get("max_time_taken_sec") is not None and meta.get("time_taken_sec", float('inf')) > validators["max_time_taken_sec"]:
                return False, f"Quiz time {meta.get('time_taken_sec', 'N/A')}s exceeds max."
        elif type == "help_post":
            if validators.get("min_word_count") is not None and meta.get("word_count", 0) < validators["min_word_count"]:
                return False, f"Help post word count {meta.get('word_count',0)} below min {validators['min_word_count']}."
        return True, None

    def process_user_actions(self, uid: str, event_dt_utc: datetime, actions_load: List[Dict[str, Any]]) -> Dict[str, StreakInfo]:
        logger.info(f"Processing for user '{uid}', event_dt: {event_dt_utc}")
        if uid not in user_streaks_db: user_streaks_db[uid] = {}
        
        user_data = user_streaks_db[uid]
        processed_payload_info: Dict[str, StreakInfo] = {}
        current_event_dt_date = get_utc_date(event_dt_utc)
        
        processed_types_in_req = set()

        # Loop 1: Process actions present in the current request's payload
        for item in actions_load:
            act_type = item.get("type")
            meta = item.get("metadata", {})
            processed_types_in_req.add(act_type)
            act_cfg = AppConfig.get(f"activity_types.{act_type}")

            if not act_cfg or not act_cfg.get("enabled"):
                logger.warning(f"Action '{act_type}' not configured/enabled. Skipping."); continue

            last_info = user_data.get(act_type, {})
            streak_db = last_info.get("current_streak", 0)
            last_event_d = last_info.get("last_event_date", None)
            status_db = last_info.get("status", "none")

            logger.debug(f"[{act_type}] DB Before: S={streak_db}, Date={last_event_d}, Status={status_db}")

            is_valid, reason = self._validate_action_metadata(act_type, meta, act_cfg)
            logger.debug(f"[{act_type}] Initial validation: {is_valid}, Reason: {reason}")
            if is_valid and act_type == "help_post" and act_cfg.get("validators", {}).get("ai_validation_enabled"):
                logger.debug(f"[{act_type}] Starting AI validation")
                if ContentValidator._model_pipeline is None:
                    try: 
                        ContentValidator.load_model()
                        logger.debug(f"[{act_type}] AI model loaded successfully")
                    except Exception as e: 
                        logger.error(f"[{act_type}] AI model load failed: {e}")
                        is_valid, reason = False, f"AI model load fail: {e}"
                if ContentValidator._model_pipeline: 
                    logger.debug(f"[{act_type}] Running AI validation on content: {meta.get('content', '')[:100]}...")
                    is_valid, reason, _ = ContentValidator.validate_content(meta.get("content", ""))
                    logger.debug(f"[{act_type}] AI validation result: {is_valid}, Reason: {reason}")
                    if not is_valid:
                        logger.debug(f"[{act_type}] AI validation failed: {reason}")
            
            logger.debug(f"[{act_type}] Final validation: {is_valid}, Reason: {reason}")

            out_streak = streak_db
            out_status = "active" if status_db == "none" else status_db 
            date_counts_for = current_event_dt_date

            if not is_valid:
                logger.debug(f"[{act_type}] Action not valid. Current state: streak={streak_db}, status={status_db}, last_date={last_event_d}")
                if last_event_d and streak_db > 0: 
                    eff_dl_old = calculate_strict_deadline_for_next_day_action(last_event_d) + timedelta(hours=AppConfig.get("grace_period_hours",0))
                    if event_dt_utc > eff_dl_old: out_streak, out_status, date_counts_for = 0, "lost", None
                    else: out_status, date_counts_for = "active", last_event_d 
                else: out_streak, out_status, date_counts_for = 0, "none", None 
            else: # IS VALID
                logger.debug(f"[{act_type}] Action is valid. Current state: streak={streak_db}, status={status_db}, last_date={last_event_d}")
                out_status = "active" 
                if last_event_d is None: 
                    out_streak = 1; date_counts_for = current_event_dt_date
                    logger.debug(f"[{act_type}] First valid action. S=1, St=active, Date={date_counts_for}")
                elif current_event_dt_date == last_event_d: 
                    date_counts_for = last_event_d
                    logger.debug(f"[{act_type}] Same day valid action. S={out_streak}, St=active, Date={date_counts_for}")
                else:
                    expected_continue_day = last_event_d + timedelta(days=1)
                    eff_dl_expected = calculate_strict_deadline_for_next_day_action(last_event_d) + timedelta(hours=AppConfig.get("grace_period_hours",0))
                    if uid == FAILING_TEST_USER_ID_FOR_LOGGING and act_type == 'login': 
                        logger.info(f"DEBUG_GRACE_VALID [{act_type} for {uid}]: event_dt_utc={event_dt_utc.isoformat()}, eff_dl_expected={eff_dl_expected.isoformat()}, condition={event_dt_utc <= eff_dl_expected}")
                    if event_dt_utc <= eff_dl_expected:
                        out_streak = streak_db + 1; date_counts_for = expected_continue_day
                        logger.debug(f"[{act_type}] Streak continued. S={out_streak}, St=active, Date={date_counts_for}")
                    else: 
                        out_streak = 1; date_counts_for = current_event_dt_date
                        logger.info(f"[{act_type}] Streak broken, new started. S=1, St=active, Date={date_counts_for}")
            
            # Ensure last_event_date is always set for valid actions
            if out_status == "active" and date_counts_for is None:
                date_counts_for = current_event_dt_date  # Defensive: should never be None for valid actions
            user_data[act_type] = {"current_streak": out_streak, "last_event_date": date_counts_for if out_status not in ["lost", "none"] else None, "status": out_status}
            if uid == FAILING_TEST_USER_ID_FOR_LOGGING and act_type == "help_post": logger.info(f"SPECIAL_LOG [{act_type} for {uid}]: Loop 1 DB Update: {user_data[act_type]}")

            next_dl = None
            if out_status == "active" and out_streak > 0 and date_counts_for: next_dl = calculate_strict_deadline_for_next_day_action(date_counts_for)
            processed_payload_info[act_type] = StreakInfo(current_streak=out_streak, status=out_status, tier=get_streak_tier_name(out_streak), next_deadline_utc=next_dl, validated=is_valid, rejection_reason=reason if not is_valid else None)

        # DEBUG: Print user_data after first loop
        logger.info(f"DEBUG: user_data after first loop for user '{uid}': {user_data}")

        # Loop 2: Construct the final response object
        final_output: Dict[str, StreakInfo] = {}
        for act_type_out in user_data.keys():
            db_state = user_data[act_type_out]
            s = db_state.get("current_streak",0); st = db_state.get("status","none"); d = db_state.get("last_event_date",None)
            n_dl, val, rej = None, None, None

            if payload_info := processed_payload_info.get(act_type_out): 
                val, rej = payload_info.validated, payload_info.rejection_reason
            elif d and s > 0 and st == "active": 
                eff_dl = calculate_strict_deadline_for_next_day_action(d) + timedelta(hours=AppConfig.get("grace_period_hours",0))
                if event_dt_utc > eff_dl: 
                    s_new, st_new, d_new = 0, "lost", None 
                    user_data[act_type_out] = {"current_streak":s_new, "status":st_new, "last_event_date":d_new} 
                    s, st, d = s_new, st_new, d_new 
                # else: n_dl will be calculated based on existing 'd' if still active
            elif s == 0 and st != "lost" and act_type_out not in processed_types_in_req: 
                st = "lost" if d else "none"; user_data[act_type_out]["status"] = st 
            
            current_final_streak = user_data[act_type_out]["current_streak"]
            current_final_status = user_data[act_type_out]["status"]
            current_final_last_date = user_data[act_type_out]["last_event_date"]

            if current_final_status == "active" and current_final_streak > 0 and current_final_last_date:
                n_dl = calculate_strict_deadline_for_next_day_action(current_final_last_date)
            else: 
                n_dl = None

            final_output[act_type_out] = StreakInfo(
                current_streak=current_final_streak, 
                status=current_final_status,       
                tier=get_streak_tier_name(current_final_streak),
                next_deadline_utc=n_dl,
                validated=val, 
                rejection_reason=rej 
            )
            if uid == FAILING_TEST_USER_ID_FOR_LOGGING and act_type_out == "help_post": 
                logger.info(f"SPECIAL_LOG [{act_type_out} for {uid}]: Final Output Entry: {final_output[act_type_out].model_dump_json(indent=2)}")
        
        logger.info(f"Final response for user '{uid}': {final_output}")
        return final_output