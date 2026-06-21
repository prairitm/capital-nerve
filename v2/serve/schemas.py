"""Request bodies for the serving layer.

Responses are assembled as plain dicts in `mapper.py` to mirror the exact JSON
shapes in `v1/frontend/src/api/types.ts`; only inbound payloads need parsing,
so those are the models defined here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None


class WatchlistCompanyRequest(BaseModel):
    company_id: int


class WatchItemCreateRequest(BaseModel):
    company_id: int | None = None
    card_id: int | None = None
    metric_def_id: int | None = None
    title: str
    description: str | None = None
    target_value: float | None = None
    condition_operator: str | None = None
    condition_json: dict = Field(default_factory=dict)


class WatchItemPatchRequest(BaseModel):
    is_active: bool | None = None
    title: str | None = None
    description: str | None = None


class AskRequest(BaseModel):
    q: str = Field(min_length=1)
    company_id: int | None = None
    event_id: int | None = None


class CreateCompanyRequest(BaseModel):
    company_name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    sector_id: int | None = None
    industry: str | None = None


class ReviewPatchRequest(BaseModel):
    status: str
