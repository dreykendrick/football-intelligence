from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def list_models():
    """Placeholder endpoint for model registry versions."""
    return {"message": "Models endpoint operational. Implementation scheduled for Sprint 1.3+"}
