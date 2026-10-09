from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def list_matches():
    """Placeholder endpoint for listing match fixtures."""
    return {"message": "Matches endpoint operational. Implementation scheduled for Sprint 1.2+"}
