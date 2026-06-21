# schemas/auth

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Pydantic shapes for the authentication flow.

## Source

- Path: `backend/app/schemas/auth.py`
- Layer: backend-schemas

## Contract

- `SignupRequest` — `email: EmailStr`, `password: str = Field(min_length=6)`, `full_name: str | None = None`.
- `LoginRequest` — `email: EmailStr`, `password: str`.
- `TokenResponse` — `access_token`, `token_type="bearer"`, `user_id`, `email`, `user_type: UserType`, `full_name`.
- `UserResponse` — `user_id`, `email`, `full_name`, `user_type`. Uses `class Config: from_attributes = True` so it accepts an ORM `AppUser`.

## Dependencies

- Imports `pydantic.BaseModel`, `EmailStr`, `Field`; `UserType` from enums.

## Patterns (symmetry)

- Password minimum length is `6`. Mirror this in [`../../../frontend/src/pages/SignupPage.tsx`](../../../frontend/src/pages/SignupPage.tsx) (`minLength={6}`).
- `UserResponse` is the only schema in the app with `from_attributes = True`. Do not propagate the pattern to other schemas — keep manual mapping the default.
- `TokenResponse.email` is the user's email and is always set on login / signup (auth router falls back to `""` when nullable on `AppUser`).

## Verification checklist

- [ ] Password length constraint kept in sync with the frontend
- [ ] `from_attributes` remains an opt-in only for `UserResponse`
- [ ] Field additions mirrored in `frontend/src/api/types.ts` (`UserPayload`, `TokenResponse`)
