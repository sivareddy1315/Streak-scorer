from pydantic import BaseModel, Field, field_validator # Use field_validator for Pydantic V2
from typing import List, Dict, Any, Optional # Ensure Optional is here
from datetime import datetime

# --- Input Models ---
class LoginMetadata(BaseModel):
    pass 

class QuizMetadata(BaseModel):
    quiz_id: str
    score: int
    time_taken_sec: int

class HelpPostMetadata(BaseModel):
    content: str
    word_count: int 
    contains_code: bool 

class ActionItem(BaseModel):
    type: str
    metadata: Dict[str, Any] 

    @field_validator('type') # Pydantic V2 style
    @classmethod
    def validate_action_type_v2(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Action type cannot be empty.")
        return value

class StreakUpdateRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    date_utc: datetime 
    actions: List[ActionItem] = Field(..., min_length=1) # Changed min_items to min_length

# --- Output Models ---
class StreakInfo(BaseModel):
    current_streak: int
    status: str 
    tier: str   
    next_deadline_utc: Optional[datetime] = None # Already uses Optional
    validated: Optional[bool] = None 
    rejection_reason: Optional[str] = None

class StreakUpdateResponse(BaseModel):
    user_id: str
    streaks: Dict[str, StreakInfo] 