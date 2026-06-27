"""FastAPI service for financial_result_flow.ipynb Step 1 / 7.

Run from this directory:
    uvicorn company:app --host 127.0.0.1 --port 8020 --reload
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from company_config import settings
from company_db import get_conn
from company_models import (
    CompanyResponse,
    RegisterCompanyRequest,
    RegisterCompanyResponse,
)
from company_service import register_company

app = FastAPI(title="CapitalNerve Company Step Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {"ok": True, "db_path": str(settings.db_path)}


@app.post("/companies", response_model=RegisterCompanyResponse)
def create_company(payload: RegisterCompanyRequest) -> RegisterCompanyResponse:
    with get_conn() as conn:
        company = register_company(conn, payload.symbol)
    return RegisterCompanyResponse(
        db_path=str(settings.db_path),
        company=CompanyResponse(**company),
    )


if __name__ == "__main__":
    uvicorn.run("company:app", host="127.0.0.1", port=8020, reload=True)
