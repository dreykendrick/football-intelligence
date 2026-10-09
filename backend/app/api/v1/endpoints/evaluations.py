from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def list_evaluations():
    """Placeholder endpoint for backtesting and model evaluation results."""
    return {"message": "Evaluations endpoint operational. Implementation scheduled for Sprint 1.4+"}
