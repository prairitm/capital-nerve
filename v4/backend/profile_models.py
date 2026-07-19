"""Profile and email-notification API models."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class ProfileResponse(BaseModel):
    full_name: str | None
    login_email: EmailStr
    notification_email: EmailStr
    email_enabled: bool
    email_verified: bool
    verification_required: bool
    financial_results_enabled: bool
    investor_presentations_enabled: bool
    earnings_calls_enabled: bool


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)
    notification_email: EmailStr
    email_enabled: bool
    financial_results_enabled: bool = True
    investor_presentations_enabled: bool = True
    earnings_calls_enabled: bool = True
