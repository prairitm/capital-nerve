"""Request and response models for the Step 1 company microservice."""

from __future__ import annotations

from pydantic import BaseModel, Field, validator


class RegisterCompanyRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])

    @validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        return symbol


class CompanyResponse(BaseModel):
    id: str
    name: str
    ticker: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    isin: str | None = None


class RegisterCompanyResponse(BaseModel):
    db_path: str
    company: CompanyResponse
