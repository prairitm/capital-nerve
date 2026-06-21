# db/base

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Declarative base for every SQLAlchemy 2.0 model.

## Source

- Path: `backend/app/db/base.py`
- Layer: backend-db

## Contract

- Exports `class Base(DeclarativeBase): pass`.
- Every model in [`../models/`](../models/) subclasses this `Base`.

## Dependencies

- Imports `DeclarativeBase` from `sqlalchemy.orm`.

## Patterns (symmetry)

- One `Base` per app. Do not introduce another.
- Keep this file deliberately empty beyond the class — adding metadata, naming conventions, or mixins here would create circular imports.

## Verification checklist

- [ ] Only one `Base` exists in the app
- [ ] Every new model imports it from `app.db.base`
