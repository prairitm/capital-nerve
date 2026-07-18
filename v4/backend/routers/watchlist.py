"""Private per-user company watchlists."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app_db import get_app_conn, utc_iso
from db import get_conn
from routers.companies import build_company_list
from security import CurrentUser, api_error, require_ready_user

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def get_watchlist(user: CurrentUser = Depends(require_ready_user)):
    with get_app_conn() as app_conn:
        ids = [
            row["company_id"]
            for row in app_conn.execute(
                """
                SELECT company_id FROM watchlist_companies
                WHERE user_id = ? ORDER BY added_at DESC
                """,
                (user.id,),
            ).fetchall()
        ]
    if not ids:
        return {"companies": [], "count": 0}
    with get_conn() as conn:
        companies = build_company_list(
            conn,
            company_ids=ids,
            limit=len(ids),
            watched_company_ids=set(ids),
        )
    by_id = {company["id"]: company for company in companies}
    ordered = [by_id[company_id] for company_id in ids if company_id in by_id]
    return {"companies": ordered, "count": len(ordered)}


@router.put("/companies/{company_id}")
def add_company(company_id: str, user: CurrentUser = Depends(require_ready_user)):
    with get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not exists:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "company_not_found",
            "Company not found.",
        )
    with get_app_conn() as conn:
        now = utc_iso()
        had_watchers = conn.execute(
            """
            SELECT 1 FROM watchlist_companies w
            JOIN users u ON u.id = w.user_id
            WHERE w.company_id = ? AND u.is_active = 1
            LIMIT 1
            """,
            (company_id,),
        ).fetchone() is not None
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO watchlist_companies(user_id, company_id, added_at)
            VALUES (?, ?, ?)
            """,
            (user.id, company_id, now),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO company_poll_state(
                company_id, baseline_at, next_poll_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (company_id, now, now, now, now),
        )
        if had_watchers:
            conn.execute(
                """
                UPDATE company_poll_state
                SET next_poll_at = CASE WHEN next_poll_at > ? THEN ? ELSE next_poll_at END,
                    updated_at = ?
                WHERE company_id = ?
                """,
                (now, now, now, company_id),
            )
        else:
            conn.execute(
                """
                UPDATE company_poll_state
                SET baseline_at = ?, last_success_at = NULL, next_poll_at = ?,
                    lease_until = NULL, last_error = NULL, consecutive_failures = 0,
                    updated_at = ?
                WHERE company_id = ?
                """,
                (now, now, now, company_id),
            )
        conn.commit()
    return {"watchlist_status": True, "added": cursor.rowcount > 0}


@router.delete("/companies/{company_id}")
def remove_company(company_id: str, user: CurrentUser = Depends(require_ready_user)):
    with get_app_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM watchlist_companies WHERE user_id = ? AND company_id = ?",
            (user.id, company_id),
        )
        conn.commit()
    return {"watchlist_status": False, "removed": cursor.rowcount > 0}
