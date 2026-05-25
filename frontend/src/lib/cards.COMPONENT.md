# lib/cards

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Feed transforms for the intelligence card list: filter the `watch_next` card type out, keep only signal-fired and summary cards, sort by time, and group by event for the timeline view.

## Source

- Path: `frontend/src/lib/cards.ts`
- Layer: frontend-lib

## Contract

- Exports:
  - `intelligenceObjectBriefToCardBrief(d)` — adapter from v1 `IntelligenceObjectBrief` to legacy `CardBrief` (includes `event_type`).
  - `intelligenceObjectToCardBrief(d)` — adapter from v1 `IntelligenceObject` to legacy `CardBrief`.
  - `filterInsightListCards(cards)` — drops the `watch_next` card type.
  - `filterSignalFiredCards(cards)` — keeps cards with `signal_id`, plus the explicit summary types in `SUMMARY_CARD_TYPES`.
  - `filterHomeFeedCards(cards, _tab?)` — insight-list filter plus signal-fired filter; the tab argument is accepted but ignored (kept for call-site compatibility).
  - `sortCardsByTime(cards)` — newest first by `event_date` (fallback `created_at`).
  - `interface TimelineCardGroup { key; event; eventDate; eventLabel; eventType; cards }`
  - `groupCardsByTimeline(cards, timeline)` — groups cards into the order of `timeline`, then appends orphan events and an `Other` ungrouped bucket.
  - `groupCardsByEvent(cards)` — groups cards by their `event_id` without a timeline reference.
  - `groupEventsByQuarter(events)` — groups `TimelineEvent` / `EventBriefV1` rows by `period.period_id`, newest quarter first.

## Dependencies

- Imports types only from `@/api/types`.
- No React, router, or API calls.

## Patterns (symmetry)

- `INSIGHT_LIST_EXCLUDED_TYPES` is the source of truth for hidden card types. Add to this set rather than filtering ad hoc in pages.
- `SUMMARY_CARD_TYPES` mirrors `SUMMARY_CARD_TYPES` in `backend/app/services/pipeline/cards.py`. Cards in this set are produced by the pipeline as aggregate heroes (no `signal_id`) and must remain visible on the home feed.
- Sorting uses `bMs - aMs` (newest first); ties break on `created_at` so multi-card events stay deterministic.
- Group `key`s are `"event-${event_id}"` for grouped buckets and `"ungrouped"` for the fallback. The timeline component depends on these keys.

## Verification checklist

- [ ] No React imports
- [ ] Hidden card types updated in `INSIGHT_LIST_EXCLUDED_TYPES`; aggregate summary types updated in `SUMMARY_CARD_TYPES`
- [ ] Group keys remain `"event-:id"` and `"ungrouped"`
- [ ] Sorting is deterministic (created_at tiebreaker preserved)
