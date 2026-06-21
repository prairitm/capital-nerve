from pydantic import BaseModel, EmailStr, Field

from app.db.enums import UserType


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    user_type: UserType
    full_name: str | None = None


class UserResponse(BaseModel):
    user_id: int
    email: str | None
    full_name: str | None
    user_type: UserType

    class Config:
        from_attributes = True
