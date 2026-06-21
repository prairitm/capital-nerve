"""Review router — the v2 notebook auto-publishes, so the queue is empty."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..schemas import ReviewPatchRequest
from ..state import User

router = APIRouter(prefix="/review", tags=["review"])


@router.get("")
def list_reviews(
    status_filter: str | None = None,
    user: User = Depends(get_current_user),
) -> list[dict]:
    # The v2 pipeline writes accepted metrics directly; nothing is held for review.
    return []


@router.get("/{review_id}/pipeline")
def review_pipeline(review_id: int, user: User = Depends(get_current_user)) -> dict:
    raise HTTPException(status_code=404, detail="Review item not found")


@router.patch("/{review_id}")
def patch_review(
    review_id: int,
    body: ReviewPatchRequest,
    user: User = Depends(get_current_user),
) -> dict:
    return {"ok": True, "review_id": review_id, "status": body.status}
