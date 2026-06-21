# models/__init__

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Re-export every ORM model so Alembic autogenerate can discover all tables in one import.

## Source

- Path: `backend/app/models/__init__.py`
- Layer: backend-db

## Contract

- Re-exports every class declared under `app.models.*` via `from app.models.<file> import ...`.
- Maintains `__all__` listing every model alphabetically.

## Dependencies

- Imports from `app.models.events`, `app.models.facts`, `app.models.intelligence`, `app.models.master`, `app.models.review`, `app.models.user`.

## Patterns (symmetry)

- When you add a new model:
  1. Add it to the right domain file under `app/models/`.
  2. Add an import line here.
  3. Add the class name to `__all__` (alphabetical).
- Do not put model definitions in this file.

## Verification checklist

- [ ] Every model imported here
- [ ] `__all__` alphabetized
- [ ] Alembic autogenerate picks up the new model
