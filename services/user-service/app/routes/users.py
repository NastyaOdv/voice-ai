from fastapi import APIRouter, Depends

from app.utils.dependencies import get_current_user_id

router = APIRouter(tags=["users"])


@router.get("/me")
async def me(user_id: str = Depends(get_current_user_id)) -> dict[str, str]:
    """Protected example: requires a valid access token issued by auth-service."""
    return {"user_id": user_id}
