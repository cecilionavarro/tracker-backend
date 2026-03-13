from fastapi import APIRouter

router = APIRouter()

# Change @router.post("/") to this:
@router.get("/health")
async def health():
    return {"status": "healthy"}