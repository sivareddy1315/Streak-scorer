import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import status, FastAPI 
import os
from datetime import datetime, timedelta, timezone
from app.ai.validator import ContentValidator
from unittest.mock import patch

# Try to import app and config
try:
    from app.main import app # Your FastAPI application
    from app.core.config import AppConfig 
except ImportError:
    # Fallback if pytest has issues with relative paths from test dir
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from app.main import app
    from app.core.config import AppConfig

BASE_URL = "http://127.0.0.1" # Base URL for the client

@pytest.fixture(scope="session")
def anyio_backend():
    # Required for async pytest functions
    return "asyncio"

@pytest.fixture(scope="function")
async def client():
    # Ensure AppConfig is fresh for each test to avoid state leakage
    AppConfig._config_data = {} 
    AppConfig._loaded = False   
    try:
        AppConfig.load_config() 
    except Exception as e:
        print(f"WARNING: Failed to load AppConfig in test client fixture: {e}")

    # Initialize ContentValidator
    try:
        ContentValidator.load_model()
        print("ContentValidator initialized successfully in test client fixture")
    except Exception as e:
        print(f"WARNING: Failed to initialize ContentValidator in test client fixture: {e}")

    # Using app.router.lifespan_context ensures startup/shutdown events run for tests
    async with app.router.lifespan_context(app): 
        transport = ASGITransport(app=app) # Pass the FastAPI app instance here
        async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
            yield ac

# --- General Endpoint Tests ---
@pytest.mark.anyio
async def test_read_root(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert "<h1>Welcome to the Streak Scoring Microservice!</h1>" in response.text

@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}

@pytest.mark.anyio
async def test_version_info(client: AsyncClient):
    response = await client.get("/version")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "service_name" in data
    assert "service_api_version" in data
    assert "ai_model_versions" in data
    assert data["service_api_version"] == AppConfig.get("service_version", "N/A - Test Default")

# --- Constants for Test User IDs ---
USER_VALID_ACTIONS = "user_valid_actions"
USER_AI_TESTS = "user_ai_tests"
USER_TIER_TESTS = "user_tier_tests"
USER_GRACE_TESTS = "user_grace_tests"
USER_TIMEOUT_TESTS = "user_timeout_tests"
USER_MALFORMED = "user_malformed_inputs"
USER_UNSUPPORTED = "user_unsupported_type"

# --- Test Cases for /streaks/update ---

# Category: Valid and Invalid Actions (Basic)
@pytest.mark.anyio
async def test_initial_valid_login(client: AsyncClient):
    uid = f"{USER_VALID_ACTIONS}_login"
    req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "login", "metadata": {}}]}
    res = await client.post("/streaks/update", json=req)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["streaks"]["login"]
    assert data["current_streak"] == 1
    assert data["status"] == "active"

@pytest.mark.anyio
async def test_initial_valid_quiz(client: AsyncClient):
    uid = f"{USER_VALID_ACTIONS}_quiz"
    req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "quiz", "metadata": {"quiz_id": "q1", "score": 8, "time_taken_sec": 100}}]}
    res = await client.post("/streaks/update", json=req)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["streaks"]["quiz"]
    assert data["current_streak"] == 1
    assert data["validated"] is True

@pytest.mark.anyio
async def test_initial_invalid_quiz_score(client: AsyncClient):
    uid = f"{USER_VALID_ACTIONS}_quiz_low_score"
    req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "quiz", "metadata": {"quiz_id": "q2", "score": 3, "time_taken_sec": 100}}]} # min_score is 5
    res = await client.post("/streaks/update", json=req)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["streaks"]["quiz"]
    assert data["current_streak"] == 0
    assert data["validated"] is False
    assert "score" in data["rejection_reason"].lower()

@pytest.mark.anyio
async def test_initial_valid_help_post_passes_ai(client: AsyncClient):
    uid = f"{USER_VALID_ACTIONS}_helppost_good"
    # This content needs to be reliably classified as GOOD by your trained AI model
    content = "This is a fantastic and detailed explanation of quicksort algorithm. It includes several code snippets and common pitfalls to avoid for optimal performance."
    req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "help_post", "metadata": {"content": content, "word_count": len(content.split()), "contains_code": True}}]}
    res = await client.post("/streaks/update", json=req)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["streaks"]["help_post"]
    assert data["validated"] is True, f"Help post rejected: {data.get('rejection_reason')}"
    assert data["current_streak"] == 1

@pytest.mark.anyio
async def test_initial_invalid_help_post_word_count(client: AsyncClient):
    uid = f"{USER_VALID_ACTIONS}_helppost_short"
    req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "help_post", "metadata": {"content": "Too short.", "word_count": 2, "contains_code": False}}]} # min_word_count is 10
    res = await client.post("/streaks/update", json=req)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["streaks"]["help_post"]
    assert data["current_streak"] == 0
    assert data["validated"] is False
    assert "word count" in data["rejection_reason"].lower()

# Category: Rejected Streak Actions via AI
@pytest.mark.anyio
async def test_help_post_rejected_by_ai(client: AsyncClient):
    uid = f"{USER_AI_TESTS}_reject"
    # This content needs to be reliably classified as BAD by your trained AI model
    content = "idk my stuff broke help me what do i do this is just filler text aaaaa bbbbb"
    req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "help_post", "metadata": {"content": content, "word_count": len(content.split()), "contains_code": False}}]}
    res = await client.post("/streaks/update", json=req)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()["streaks"]["help_post"]
    assert data["validated"] is False
    assert data["current_streak"] == 0
    assert data["rejection_reason"] is not None
    assert "AI" in data["rejection_reason"] or "quality" in data["rejection_reason"]


# Category: Tier Upgrades
@pytest.mark.anyio
async def test_tier_upgrades_login(client: AsyncClient):
    uid = f"{USER_TIER_TESTS}_login"
    base_t = datetime.now(timezone.utc)
    tiers_config = AppConfig.get("streak_tiers")
    
    # Test reaching each tier
    current_streak_val = 0
    for day_offset in range(AppConfig.get("streak_tiers")[-1]["min_streak"] + 2): # Go a bit beyond gold
        current_streak_val += 1
        action_time = base_t + timedelta(days=day_offset)
        req = {"user_id": uid, "date_utc": action_time.isoformat(), "actions": [{"type": "login", "metadata": {}}]}
        res = await client.post("/streaks/update", json=req)
        assert res.status_code == status.HTTP_200_OK
        streak_data = res.json()["streaks"]["login"]
        assert streak_data["current_streak"] == current_streak_val
        
        expected_tier = "none" # Default
        for tier_info in sorted(tiers_config, key=lambda x: x['min_streak'], reverse=True):
            if current_streak_val >= tier_info['min_streak']:
                expected_tier = tier_info['name']
                break
        assert streak_data["tier"] == expected_tier

# Category: Timeouts and Grace Logic
@pytest.mark.anyio
async def test_streak_timeout_and_break(client: AsyncClient):
    uid = f"{USER_TIMEOUT_TESTS}_break"
    base_t = datetime.now(timezone.utc)
    grace_hrs = AppConfig.get("grace_period_hours", 2)

    # Action 1: Establish streak
    res1 = await client.post("/streaks/update", json={"user_id": uid, "date_utc": base_t.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    assert res1.json()["streaks"]["login"]["current_streak"] == 1
    
    # Action 2: Skip a day (well past grace period)
    action_time_day3 = base_t + timedelta(days=2, hours=grace_hrs + 1) 
    res2 = await client.post("/streaks/update", json={"user_id": uid, "date_utc": action_time_day3.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    assert res2.json()["streaks"]["login"]["current_streak"] == 1 # Reset
    assert res2.json()["streaks"]["login"]["tier"] == AppConfig.get("streak_tiers")[0]["name"]

@pytest.mark.anyio
async def test_grace_period_saves_streak(client: AsyncClient):
    uid = f"{USER_GRACE_TESTS}_save"
    day1_action_t = datetime(2024, 7, 1, 10, 0, 0, tzinfo=timezone.utc) # Fixed date
    grace_hrs = AppConfig.get("grace_period_hours", 2)

    await client.post("/streaks/update", json={"user_id": uid, "date_utc": day1_action_t.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    # Last valid: 2024-07-01. Expected for: 2024-07-02.
    # Effective deadline for 2024-07-02 action: 2024-07-02T23:59:59Z + grace_hrs
    effective_dl_day2 = datetime(2024, 7, 2, 23, 59, 59, tzinfo=timezone.utc) + timedelta(hours=grace_hrs)
    grace_action_ts = effective_dl_day2 - timedelta(minutes=30) # Within grace

    res_grace = await client.post("/streaks/update", json={"user_id": uid, "date_utc": grace_action_ts.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    assert res_grace.status_code == status.HTTP_200_OK
    d_grace = res_grace.json()["streaks"]["login"]
    assert d_grace["current_streak"] == 2

    day_action_counted_for = day1_action_t.date() + timedelta(days=1) # 2024-07-02
    expected_next_dl_day_obj = day_action_counted_for + timedelta(days=1) # Next action on 2024-07-03
    assert d_grace["next_deadline_utc"].startswith(expected_next_dl_day_obj.strftime("%Y-%m-%d"))

@pytest.mark.anyio
async def test_grace_period_missed_breaks_streak(client: AsyncClient):
    uid = f"{USER_GRACE_TESTS}_miss"
    day1_action_t = datetime(2024, 7, 5, 10, 0, 0, tzinfo=timezone.utc)
    grace_hrs = AppConfig.get("grace_period_hours", 2)

    await client.post("/streaks/update", json={"user_id": uid, "date_utc": day1_action_t.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    # Effective deadline for 2024-07-06 action: 2024-07-06T23:59:59Z + grace_hrs
    effective_dl_day2 = datetime(2024, 7, 6, 23, 59, 59, tzinfo=timezone.utc) + timedelta(hours=grace_hrs)
    miss_grace_action_ts = effective_dl_day2 + timedelta(minutes=30) # Past grace

    res_miss = await client.post("/streaks/update", json={"user_id": uid, "date_utc": miss_grace_action_ts.isoformat(), "actions": [{"type": "login", "metadata": {}}]})
    assert res_miss.status_code == status.HTTP_200_OK
    d_miss = res_miss.json()["streaks"]["login"]
    assert d_miss["current_streak"] == 1 # Reset

# Category: Malformed Input and Unsupported Action Types
@pytest.mark.anyio
async def test_malformed_input_validation(client: AsyncClient):
    # Missing user_id
    req_no_uid = {"date_utc": datetime.now(timezone.utc).isoformat(), "actions": [{"type": "login", "metadata": {}}]}
    res_no_uid = await client.post("/streaks/update", json=req_no_uid)
    assert res_no_uid.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Invalid date format
    req_bad_date = {"user_id": f"{USER_MALFORMED}_bad_date", "date_utc": "not-a-date", "actions": [{"type": "login", "metadata": {}}]}
    res_bad_date = await client.post("/streaks/update", json=req_bad_date)
    assert res_bad_date.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    # Empty actions list
    req_empty_actions = {"user_id": f"{USER_MALFORMED}_empty_actions", "date_utc": datetime.now(timezone.utc).isoformat(), "actions": []}
    res_empty_actions = await client.post("/streaks/update", json=req_empty_actions)
    assert res_empty_actions.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

@pytest.mark.anyio
async def test_unsupported_action_type_ignored(client: AsyncClient):
    uid = f"{USER_UNSUPPORTED}_action"; req = {"user_id": uid, "date_utc": datetime.now(timezone.utc).isoformat(), "actions": [
        {"type": "login", "metadata": {}}, {"type": "this_is_not_configured", "metadata": {}}]}
    res = await client.post("/streaks/update", json=req)
    assert res.status_code == status.HTTP_200_OK
    d = res.json()
    assert "login" in d["streaks"]
    assert d["streaks"]["login"]["current_streak"] == 1
    assert "this_is_not_configured" not in d["streaks"]

# Test for ensuring all tracked streaks (including lost ones) are reported
@pytest.mark.anyio
async def test_report_all_streaks_including_lost(client: AsyncClient):
    from app.ai.validator import ContentValidator
    with patch.object(ContentValidator, 'validate_content', return_value=(True, 'Mocked valid', 1.0)):
        uid = f"{USER_TIMEOUT_TESTS}_report_lost"
        time_day1 = datetime(2024, 7, 10, 10, 0, 0, tzinfo=timezone.utc)
        time_day3_well_past_deadline = datetime(2024, 7, 13, 10, 0, 0, tzinfo=timezone.utc) # Day 1 -> deadline end of Day 2 + grace

        # Establish login and quiz streak on Day 1
        req1 = {"user_id": uid, "date_utc": time_day1.isoformat(), "actions": [
            {"type": "login", "metadata": {}},
            {"type": "quiz", "metadata": {"quiz_id":"q_lost_test", "score":10, "time_taken_sec":60}}
        ]}
        await client.post("/streaks/update", json=req1)

        # Send a new help_post action on Day 3 (login and quiz should have timed out)
        req2 = {"user_id": uid, "date_utc": time_day3_well_past_deadline.isoformat(), "actions": [
            {"type": "help_post", "metadata": {"content": "A new help post after others timed out.", "word_count":10, "contains_code":False}}
        ]}
        res2 = await client.post("/streaks/update", json=req2)
        assert res2.status_code == status.HTTP_200_OK
        streaks = res2.json()["streaks"]

        assert "login" in streaks
        assert streaks["login"]["status"] == "lost"
        assert streaks["login"]["current_streak"] == 0

        assert "quiz" in streaks
        assert streaks["quiz"]["status"] == "lost"
        assert streaks["quiz"]["current_streak"] == 0

        assert "help_post" in streaks
        assert streaks["help_post"]["status"] == "active"
        assert streaks["help_post"]["current_streak"] == 1