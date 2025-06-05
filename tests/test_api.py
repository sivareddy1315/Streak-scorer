import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import status, FastAPI 
import os
from datetime import datetime, timedelta, timezone

try:
    from app.main import app 
    from app.core.config import AppConfig 
except ImportError:
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from app.main import app
    from app.core.config import AppConfig

BASE_URL = "http://127.0.0.1"

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="function")
async def client():
    AppConfig._config_data = {} 
    AppConfig._loaded = False   
    try: AppConfig.load_config() 
    except Exception as e: print(f"WARNING: Failed to load AppConfig in test client fixture: {e}")
    async with app.router.lifespan_context(app): 
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
            yield ac

@pytest.mark.anyio
async def test_read_root(client: AsyncClient):
    response = await client.get("/"); assert response.status_code == status.HTTP_200_OK
    assert "<h1>Welcome to the Streak Scoring Microservice!</h1>" in response.text

@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health"); assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}

@pytest.mark.anyio
async def test_version_info(client: AsyncClient):
    response = await client.get("/version"); assert response.status_code == status.HTTP_200_OK
    data = response.json(); assert "service_name" in data; assert "service_api_version" in data
    assert "ai_model_versions" in data; assert data["service_api_version"] == AppConfig.get("service_version", "N/A")

TEST_USER_ID_API = "test_user_for_api_tests_final_v2" 

@pytest.mark.anyio
async def test_initial_valid_actions(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_init_valid"; req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [
        {"type": "login", "metadata": {}},
        {"type": "quiz", "metadata": {"quiz_id": "q_val", "score": 10, "time_taken_sec": 60}},
        {"type": "help_post", "metadata": {"content": "This is a valid test explanation about APIs focusing on clarity and examples.", "word_count": 15, "contains_code": False}}]}
    res = await client.post("/streaks/update", json=req); assert res.status_code == status.HTTP_200_OK
    d = res.json(); assert d["user_id"] == uid; assert d["streaks"]["login"]["current_streak"] == 1
    assert d["streaks"]["quiz"]["validated"] is True; 
    # AI Validation Test - depends on your training data
    assert d["streaks"]["help_post"]["validated"] is True, f"Help post rejected: {d['streaks']['help_post'].get('rejection_reason')}"
    assert d["streaks"]["help_post"]["current_streak"] == 1

@pytest.mark.anyio
async def test_ai_rejection_for_help_post(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_ai_reject_final"; req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": 
        [{"type": "help_post", "metadata": {"content": "idk bad gibberish short", "word_count": 5, "contains_code": False}}]}
    res = await client.post("/streaks/update", json=req); assert res.status_code == status.HTTP_200_OK
    d = res.json()["streaks"]["help_post"]; assert d["validated"] is False; assert d["current_streak"] == 0
    assert "word count" in d["rejection_reason"].lower() # Fails word count before AI

@pytest.mark.anyio
async def test_quiz_validation_failure_score(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_quiz_fail_final"; req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": 
        [{"type": "quiz", "metadata": {"quiz_id": "q_low", "score": 2, "time_taken_sec": 60}}]}
    res = await client.post("/streaks/update", json=req); assert res.status_code == status.HTTP_200_OK
    d = res.json()["streaks"]["quiz"]; assert d["current_streak"] == 0; assert d["validated"] is False; assert "score" in d["rejection_reason"].lower()

@pytest.mark.anyio
async def test_streak_continuation_and_tier_upgrade(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_tier_final"; base_t = datetime.now(timezone.utc)
    tiers = AppConfig.get("streak_tiers"); none_tier, bronze_tier = tiers[0]["name"], tiers[1]["name"]
    min_bronze = AppConfig.get("streak_tiers.1.min_streak", 3)
    for i in range(min_bronze):
        res = await client.post("/streaks/update", json={"user_id": uid, "date_utc": (base_t + timedelta(days=i)).isoformat(), "actions": [{"type": "login", "metadata": {}}]})
        assert res.status_code == status.HTTP_200_OK; s_info = res.json()["streaks"]["login"]
        assert s_info["current_streak"] == i + 1; assert s_info["tier"] == (bronze_tier if (i + 1) >= min_bronze else none_tier)

@pytest.mark.anyio
async def test_streak_break(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_break_final"; base_t = datetime.now(timezone.utc)
    await client.post("/streaks/update", json={"user_id": uid, "date_utc": base_t.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    grace_hrs = AppConfig.get("grace_period_hours", 0)
    break_t = base_t + timedelta(days=2, hours=grace_hrs + 1)
    res = await client.post("/streaks/update", json={"user_id": uid, "date_utc": break_t.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    assert res.status_code == status.HTTP_200_OK; d = res.json()["streaks"]["login"]
    assert d["current_streak"] == 1; assert d["tier"] == AppConfig.get("streak_tiers")[0]["name"]

@pytest.mark.anyio
async def test_grace_period_save(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_grace_save_final_v_corrected" 
    day1_action_time = datetime(2024, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
    grace_hours = AppConfig.get("grace_period_hours", 2)

    # Action 1: Establish streak
    await client.post("/streaks/update", json={"user_id": uid, "date_utc": day1_action_time.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    # last_event_date for login is now 2024-08-20.
    # Expected next action day to continue streak is 2024-08-21.

    # Calculate effective deadline for an action that *would count for 2024-08-21*
    effective_deadline_for_day_2_action = datetime(2024, 8, 21, 23, 59, 59, tzinfo=timezone.utc) + timedelta(hours=grace_hours)
    
    # Action 2: Occurs *within* the grace period for the 2024-08-21 action.
    # Its actual timestamp might be on 2024-08-22 (e.g., 2024-08-22T01:30:00Z if grace_hours=2)
    grace_action_timestamp = effective_deadline_for_day_2_action - timedelta(minutes=30)
    
    response_grace = await client.post("/streaks/update", json={"user_id": uid, "date_utc": grace_action_timestamp.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    
    assert response_grace.status_code == status.HTTP_200_OK
    data_grace = response_grace.json()["streaks"]["login"]
    assert data_grace["current_streak"] == 2, "Streak should have continued to 2 using grace period."

    # The action performed at grace_action_timestamp counted for the day 2024-08-21.
    # So, last_event_date in DB is now 2024-08-21.
    # Next deadline is for an action on 2024-08-22.
    # The deadline timestamp itself will be at the end of 2024-08-22.
    day_action_counted_for = datetime(2024, 8, 21).date() # This is the day the streak was maintained for
    expected_next_deadline_day_obj = day_action_counted_for + timedelta(days=1) # Next action on 2024-08-22
    
    assert data_grace["next_deadline_utc"].startswith(expected_next_deadline_day_obj.strftime("%Y-%m-%d")), \
        f"Expected next deadline to be for {expected_next_deadline_day_obj}, but got {data_grace['next_deadline_utc']}"
    
    # Check time part of deadline (assuming default buffer)
    if AppConfig.get("daily_reset_hour_utc", 0) == 0 and AppConfig.get("next_deadline_buffer_seconds", -1) == -1:
        assert data_grace["next_deadline_utc"].endswith("T23:59:59Z")


@pytest.mark.anyio
async def test_grace_period_miss(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_grace_miss_final"; day1_act_t = datetime(2024, 8, 25, 10, 0, 0, tzinfo=timezone.utc)
    grace_hrs = AppConfig.get("grace_period_hours", 2)
    await client.post("/streaks/update", json={"user_id": uid, "date_utc": day1_act_t.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    eff_dl_day2 = datetime(2024, 8, 26, 23, 59, 59, tzinfo=timezone.utc) + timedelta(hours=grace_hrs)
    miss_grace_act_ts = eff_dl_day2 + timedelta(minutes=30)
    res_miss = await client.post("/streaks/update", json={"user_id": uid, "date_utc": miss_grace_act_ts.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    assert res_miss.status_code == status.HTTP_200_OK; d_miss = res_miss.json()["streaks"]["login"]
    assert d_miss["current_streak"] == 1

@pytest.mark.anyio
async def test_malformed_input_pydantic(client: AsyncClient):
    req_no_uid = {"date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "login", "metadata": {}}]}
    res_no_uid = await client.post("/streaks/update", json=req_no_uid)
    assert res_no_uid.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    req_bad_date = {"user_id": f"{TEST_USER_ID_API}_bad_date", "date_utc": "not-a-date", "actions": [{"type": "login", "metadata": {}}]}
    res_bad_date = await client.post("/streaks/update", json=req_bad_date)
    assert res_bad_date.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

@pytest.mark.anyio
async def test_unsupported_action_type(client: AsyncClient):
    uid = f"{TEST_USER_ID_API}_unsupported_act"; req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [
        {"type": "login", "metadata": {}}, {"type": "unknown_action_type_blah", "metadata": {}}]}
    res = await client.post("/streaks/update", json=req); assert res.status_code == status.HTTP_200_OK
    d = res.json(); assert "login" in d["streaks"]; assert "unknown_action_type_blah" not in d["streaks"]