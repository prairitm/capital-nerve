"""Shared request/response models for authentication and user administration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

UserRole = Literal["MEMBER", "ADMIN"]


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool
    must_change_password: bool
    created_at: str
    updated_at: str
    last_login_at: str | None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=160)
    role: UserRole = "MEMBER"


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=160)
    role: UserRole | None = None
    is_active: bool | None = None


class TemporaryCredentialResponse(BaseModel):
    user: UserResponse
    temporary_password: str
