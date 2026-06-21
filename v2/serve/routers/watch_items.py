"""Watch-items router — analyst-saved tracking conditions kept in memory."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import ids
from ..builder import Catalog
from ..deps import catalog_dep, get_current_user
from ..schemas import WatchItemCreateRequest, WatchItemPatchRequest
from ..state import User, store

router = APIRouter(prefix="/watch-items", tags=["watch-items"])


@router.get("")
def list_watch_items(user: User = Depends(get_current_user)) -> list[dict]:
    return store.watch_items


@router.post("")
def create_watch_item(
    body: WatchItemCreateRequest,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict:
    company_name = ""
    company_symbol = None
    if body.company_id is not None:
        for ticker in catalog.tickers():
            if ids.company_id(ticker) == body.company_id:
                company_name = ticker.title()
                company_symbol = ticker
                break
    return store.add_watch_item(
        {
            "company_id": body.company_id,
            "company_name": company_name,
            "company_symbol": company_symbol,
            "card_id": body.card_id,
            "metric_def_id": body.metric_def_id,
            "title": body.title,
            "description": body.description,
            "current_value": None,
            "target_value": body.target_value,
            "condition_operator": body.condition_operator,
            "condition_json": body.condition_json,
        }
    )


@router.patch("/{watch_item_id}")
def patch_watch_item(
    watch_item_id: int,
    body: WatchItemPatchRequest,
    user: User = Depends(get_current_user),
) -> dict:
    for item in store.watch_items:
        if item["watch_item_id"] == watch_item_id:
            if body.is_active is not None:
                item["is_active"] = body.is_active
            if body.title is not None:
                item["title"] = body.title
            if body.description is not None:
                item["description"] = body.description
            return item
    raise HTTPException(status_code=404, detail="Watch item not found")


@router.delete("/{watch_item_id}")
def delete_watch_item(
    watch_item_id: int,
    user: User = Depends(get_current_user),
) -> dict:
    if not store.remove_watch_item(watch_item_id):
        raise HTTPException(status_code=404, detail="Watch item not found")
    return {"ok": True}
