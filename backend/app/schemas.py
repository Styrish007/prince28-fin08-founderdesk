from enum import Enum
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, Literal

class EntityType(str, Enum):
    PRIVATE_LIMITED = "private_limited"
    LLP = "llp"
    PARTNERSHIP = "partnership"
    SOLE_PROPRIETORSHIP = "sole_proprietorship"

class FounderCategory(str, Enum):
    GENERAL = "general"
    WOMEN = "women"
    SC_ST = "sc_st"
    STUDENT = "student"

class Sector(str, Enum):
    EDTECH = "edtech"
    FINTECH = "fintech"
    HEALTHTECH = "healthtech"
    AGRITECH = "agritech"
    DEEPTECH = "deeptech"
    OTHER = "other"

class State(str, Enum):
    TAMIL_NADU = "tamil_nadu"
    KARNATAKA = "karnataka"
    MAHARASHTRA = "maharashtra"
    DELHI = "delhi"
    GUJARAT = "gujarat"
    TELANGANA = "telangana"
    OTHER = "other"

class Answers(BaseModel):
    entity_type: EntityType
    incorporation_date: date
    is_dpiit_recognized: bool
    dpiit_recognition_date: Optional[date] = None
    is_deeptech: bool = False
    annual_turnover_lakh: float = Field(ge=0)
    prior_funding_lakh: float = Field(ge=0)
    founder_category: FounderCategory
    state: State
    sector: Sector

class SchemeResult(BaseModel):
    scheme_id: str
    scheme_name: str
    status: Literal["eligible", "near_miss", "ineligible"]
    reason: str
    failing_condition: Optional[str] = None
    deadline: Optional[str] = None
    source_url: str
    amount: Optional[str] = None

class MatchResponse(BaseModel):
    eligible: list[SchemeResult]
    near_miss: list[SchemeResult]
    ineligible: list[SchemeResult]
    evaluated_at: str
