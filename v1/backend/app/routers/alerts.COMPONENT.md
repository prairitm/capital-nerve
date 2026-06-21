# routers/alerts

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

User alert list and mark-as-read mutation.

## Source

- Path: `backend/app/routers/alerts.py`
- Prefix: `/alerts`
- Tags: `["alerts"]`
- Layer: backend-router

## Endpoints

- `GET /alerts?unread=false` — returns up to 50 alerts for the current user. Each row includes `company_name`, `company_symbol`, `event_id`, `card_id` for deep linking.
- `PATCH /alerts/{alert_id}/read` — flips `is_read=True`. 404 if not owned.

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select`, models (`Alert`, `Company`, `AppUser`).

## Patterns (symmetry)

- Outer join on `Company` so alerts without a company FK still render.
- Severity is serialized as `a.severity.value if a.severity else None` — keep enums serialized by value to match the frontend.
- The `HeaderAlerts` component caps display to 8; the backend caps to 50. Don't widen the backend cap without revisiting cache implications.

## Verification checklist

- [ ] Alert ownership enforced as 404
- [ ] `severity.value` returned (not the enum object)
- [ ] List capped at 50
- [ ] Outer join on `Company` preserved
