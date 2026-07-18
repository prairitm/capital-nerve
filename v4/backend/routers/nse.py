"""Search over the cached official NSE equity-company directory."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app_db import get_app_conn
from db import get_conn
from security import CurrentUser, require_ready_user


router = APIRouter(prefix="/nse-companies", tags=["nse-companies"])


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/search")
def search_nse_companies(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    user: CurrentUser = Depends(require_ready_user),
):
    query = q.strip()
    if not query:
        return []
    escaped = _like(query)
    contains = f"%{escaped}%"
    prefix = f"{escaped}%"
    with get_app_conn() as app_conn:
        listings = app_conn.execute(
            """
            SELECT symbol, company_name, series, listing_date, isin
            FROM nse_listings
            WHERE is_active = 1
              AND (
                symbol LIKE ? ESCAPE '\\' COLLATE NOCASE OR
                company_name LIKE ? ESCAPE '\\' COLLATE NOCASE
              )
            ORDER BY CASE
                WHEN symbol = ? COLLATE NOCASE THEN 0
                WHEN symbol LIKE ? ESCAPE '\\' COLLATE NOCASE THEN 1
                WHEN company_name LIKE ? ESCAPE '\\' COLLATE NOCASE THEN 2
                ELSE 3
            END, company_name COLLATE NOCASE
            LIMIT ?
            """,
            (contains, contains, query, prefix, prefix, limit),
        ).fetchall()
        watched_ids = {
            row["company_id"]
            for row in app_conn.execute(
                "SELECT company_id FROM watchlist_companies WHERE user_id = ?", (user.id,)
            )
        }
    if not listings:
        return []
    symbols = [row["symbol"] for row in listings]
    placeholders = ",".join("?" for _ in symbols)
    with get_conn() as conn:
        companies = conn.execute(
            f"SELECT id, ticker FROM companies WHERE ticker IN ({placeholders}) COLLATE NOCASE",
            symbols,
        ).fetchall()
    by_symbol = {str(row["ticker"]).upper(): row["id"] for row in companies}
    return [
        {
            **dict(row),
            "name": row["company_name"],
            "company_id": by_symbol.get(str(row["symbol"]).upper()),
            "coverage_status": (
                "watched"
                if by_symbol.get(str(row["symbol"]).upper()) in watched_ids
                else "covered"
                if by_symbol.get(str(row["symbol"]).upper())
                else "available"
            ),
        }
        for row in listings
    ]
