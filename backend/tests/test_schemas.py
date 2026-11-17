from app.schemas import Answers, EntityType, FounderCategory, State, Sector
from datetime import date

def test_answers_schema_valid():
    data = {
        "entity_type": "private_limited",
        "incorporation_date": "2024-01-15",
        "is_dpiit_recognized": True,
        "dpiit_recognition_date": "2024-02-01",
        "is_deeptech": False,
        "annual_turnover_lakh": 50,
        "prior_funding_lakh": 5,
        "founder_category": "general",
        "state": "tamil_nadu",
        "sector": "edtech"
    }
    answers = Answers(**data)
    assert answers.entity_type == EntityType.PRIVATE_LIMITED
    assert answers.prior_funding_lakh == 5

def test_answers_schema_invalid_entity_type():
    data = {
        "entity_type": "invalid_type",
        "incorporation_date": "2024-01-15",
        "is_dpiit_recognized": True,
        "annual_turnover_lakh": 50,
        "prior_funding_lakh": 5,
        "founder_category": "general",
        "state": "tamil_nadu",
        "sector": "edtech"
    }
    try:
        Answers(**data)
        assert False, "Should have raised validation error"
    except Exception:
        pass