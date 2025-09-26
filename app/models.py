from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Identity(BaseModel):
    user_id: int
    company_id: Optional[int] = None
    department_id: Optional[int] = None
    role: Optional[str] = None


class AskRequest(BaseModel):
    question: str
    identity: Identity
    limit: int = Field(default=200, ge=1, le=10000)


class GeneratedSQL(BaseModel):
    sql: str
    needs_clarification: bool = False
    clarification_question: str = ""


class AskResponse(BaseModel):
    sql: str
    needs_clarification: bool
    clarification_question: str
    rows: List[Dict[str, Any]]
    explanation: str
