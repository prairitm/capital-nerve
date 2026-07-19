"""Administrator-only review queue for uncertain extracted facts."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app_db import get_app_conn, utc_iso
from db import get_conn
from reviews import (
    AppliedReviewDecisionError,
    InvalidReviewDecisionError,
    ReviewNotFoundError,
    list_review_items,
    record_review_decision,
    reopen_review,
    review_summary,
)
from security import CurrentUser, api_error, require_admin

router = APIRouter(prefix="/admin/reviews", tags=["admin-reviews"])


class ReviewDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    selected_observation_id: str | None = None
    reviewer_note: str | None = Field(default=None, max_length=2000)


@router.get("")
def get_reviews(
    queue_status: Literal["open", "approved", "rejected", "all"] = "open",
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=200, ge=1, le=1000),
    _: CurrentUser = Depends(require_admin),
):
    with get_conn() as analytics_conn, get_app_conn() as app_conn:
        items = list_review_items(
            analytics_conn,
            app_conn,
            status=queue_status,
            search=search,
            limit=limit,
        )
        return {"items": items, "count": len(items)}


@router.get("/summary")
def get_review_summary(_: CurrentUser = Depends(require_admin)):
    with get_conn() as analytics_conn, get_app_conn() as app_conn:
        return review_summary(analytics_conn, app_conn)


@router.post("/{resolved_fact_id}/decision")
def decide_review(
    resolved_fact_id: str,
    body: ReviewDecisionRequest,
    admin: CurrentUser = Depends(require_admin),
):
    try:
        with get_conn() as analytics_conn, get_app_conn() as app_conn:
            return record_review_decision(
                analytics_conn,
                app_conn,
                resolved_fact_id=resolved_fact_id,
                decision=body.decision,
                selected_observation_id=body.selected_observation_id,
                reviewer_note=body.reviewer_note,
                reviewed_by=admin.id,
                timestamp=utc_iso(),
            )
    except ReviewNotFoundError as exc:
        raise api_error(
            status.HTTP_404_NOT_FOUND, "review_not_found", str(exc)
        ) from exc
    except InvalidReviewDecisionError as exc:
        raise api_error(
            status.HTTP_400_BAD_REQUEST, "invalid_review_decision", str(exc)
        ) from exc


@router.delete("/{resolved_fact_id}/decision")
def reopen_review_item(
    resolved_fact_id: str,
    _: CurrentUser = Depends(require_admin),
):
    try:
        with get_app_conn() as app_conn:
            if not reopen_review(app_conn, resolved_fact_id):
                raise api_error(
                    status.HTTP_404_NOT_FOUND,
                    "review_decision_not_found",
                    "Review decision not found.",
                )
    except AppliedReviewDecisionError as exc:
        raise api_error(
            status.HTTP_409_CONFLICT, "review_already_applied", str(exc)
        ) from exc
    return {"reopened": True}
