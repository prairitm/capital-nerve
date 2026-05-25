import type {
  CardBrief,
  DocumentBrief,
  EventType,
  IntelligenceObject,
  IntelligenceObjectBrief,
  PeriodBrief,
  TimelineEvent,
} from "@/api/types";
import { eventTitleToPeriodLabel, resolveQuarterPeriodLabel } from "@/lib/format";

/**
 * Narrative intelligence card types (concall / presentation). Keep in sync with
 * `CONCALL_CARD_TYPES` in `backend/app/services/card_context.py`.
 */
export const MANAGEMENT_TONE_CARD_TYPES = new Set([
  "management_tone",
  "guidance_tracker",
  "analyst_concern",
]);

/** @deprecated Use `MANAGEMENT_TONE_CARD_TYPES`. */
export const CONCALL_CARD_TYPES = MANAGEMENT_TONE_CARD_TYPES;

const MANAGEMENT_TONE_EVENT_TYPES = new Set<EventType>([
  "CONCALL_TRANSCRIPT",
  "INVESTOR_PRESENTATION",
]);

const MANAGEMENT_TONE_DOCUMENT_TYPES = new Set([
  "CONCALL_TRANSCRIPT",
  "INVESTOR_PRESENTATION",
]);

/** True when the event or any linked document is a concall transcript or investor presentation. */
export function showsManagementToneIntelligence(
  eventType: EventType,
  documents: Pick<DocumentBrief, "document_type">[],
): boolean {
  return (
    MANAGEMENT_TONE_EVENT_TYPES.has(eventType) ||
    documents.some((d) => MANAGEMENT_TONE_DOCUMENT_TYPES.has(d.document_type))
  );
}

/** @deprecated Use `showsManagementToneIntelligence`. */
export function isConcallOrTranscriptEvent(
  eventType: EventType,
  documents: Pick<DocumentBrief, "document_type">[],
): boolean {
  return showsManagementToneIntelligence(eventType, documents);
}

export function partitionManagementToneCards(cards: CardBrief[]): {
  toneCards: CardBrief[];
  otherCards: CardBrief[];
} {
  const toneCards: CardBrief[] = [];
  const otherCards: CardBrief[] = [];
  for (const card of cards) {
    if (MANAGEMENT_TONE_CARD_TYPES.has(card.card_type)) {
      toneCards.push(card);
    } else {
      otherCards.push(card);
    }
  }
  return { toneCards, otherCards };
}

/** @deprecated Use `partitionManagementToneCards`. */
export function partitionConcallCards(cards: CardBrief[]): {
  toneCards: CardBrief[];
  otherCards: CardBrief[];
} {
  return partitionManagementToneCards(cards);
}

/** Map a v1 feed brief to `CardBrief` for timeline / card components. */
export function intelligenceObjectBriefToCardBrief(
  d: IntelligenceObjectBrief,
): CardBrief {
  return {
    card_id: d.intelligence_object_id,
    signal_id: d.signal_id,
    card_type: d.object_type,
    headline: d.title,
    one_line_summary: d.subtitle,
    signal_direction: d.status,
    severity: d.severity,
    confidence_score: d.confidence_score,
    confidence_level: d.confidence,
    card_priority: d.importance_score,
    company: d.company,
    period: d.period,
    event_id: d.event_id,
    event_type: d.event_type,
    event_title: d.event_title,
    event_date: d.event_date,
    metrics_json: [],
    watch_next: null,
    source_label: null,
    document_id: null,
    created_at: d.created_at,
  };
}

/**
 * Adapt a v1 `IntelligenceObject` back to the legacy `CardBrief` shape so
 * existing dialogs (`SaveWatchItemDialog`) and feed widgets that still consume
 * `CardBrief` keep working with the upgraded drawer.
 *
 * Keep this in sync with `backend/app/schemas/v1/intelligence_object.py` —
 * each property here mirrors a field on `IntelligenceObject`.
 */
export function intelligenceObjectToCardBrief(d: IntelligenceObject): CardBrief {
  return {
    card_id: d.intelligence_object_id,
    signal_id: d.signal?.signal_id ?? null,
    card_type: d.object_type,
    headline: d.title,
    one_line_summary: d.subtitle,
    signal_direction: d.status,
    severity: d.severity,
    confidence_score: d.confidence_score,
    confidence_level: d.confidence,
    card_priority: d.importance_score,
    company: d.company,
    period: d.period,
    event_id: d.event?.event_id ?? null,
    event_type: d.event?.event_type ?? null,
    event_title: d.event?.event_title ?? null,
    event_date: d.event?.event_date ?? null,
    metrics_json: d.metrics.map((m) => ({
      name: m.name,
      value: m.value ?? "",
      unit: m.unit ?? undefined,
    })),
    watch_next: d.watch_next,
    source_label: d.source_label,
    document_id: d.document_id,
    created_at: d.created_at,
  };
}

const INSIGHT_LIST_EXCLUDED_TYPES = new Set(["watch_next"]);

/** Cards hidden from feeds and insight lists (watch-next lives on event/company summary). */
export function filterInsightListCards(cards: CardBrief[]): CardBrief[] {
  return cards.filter((c) => !INSIGHT_LIST_EXCLUDED_TYPES.has(c.card_type));
}

/**
 * Card types that aggregate an entire event rather than encode a single
 * fired signal. The pipeline writes these without a `signal_id`, so the feed
 * filter must allow them through alongside signal-linked cards. Keep in sync
 * with `SUMMARY_CARD_TYPES` in `backend/app/services/pipeline/cards.py`.
 */
const SUMMARY_CARD_TYPES = new Set(["result_verdict"]);

/** Cards backed by a `generated_signals` row or by a summary card type. */
export function filterSignalFiredCards(cards: CardBrief[]): CardBrief[] {
  return cards.filter(
    (c) => c.signal_id != null || SUMMARY_CARD_TYPES.has(c.card_type),
  );
}

/**
 * Home / watchlist feed filter: hide watch-next cards and keep only cards
 * that the pipeline produced from a signal or summary aggregator. The
 * legacy tab argument is accepted to preserve the call sites but no longer
 * relaxes the signal-id requirement.
 */
export function filterHomeFeedCards(
  cards: CardBrief[],
  _tab: string = "all",
): CardBrief[] {
  return filterSignalFiredCards(filterInsightListCards(cards));
}

export function sortCardsByTime(cards: CardBrief[]): CardBrief[] {
  return [...cards].sort((a, b) => {
    const aMs = a.event_date
      ? new Date(a.event_date).getTime()
      : new Date(a.created_at).getTime();
    const bMs = b.event_date
      ? new Date(b.event_date).getTime()
      : new Date(b.created_at).getTime();
    if (bMs !== aMs) return bMs - aMs;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
}

export interface TimelineCardGroup {
  key: string;
  event: TimelineEvent | null;
  eventDate: string | null;
  eventLabel: string | null;
  eventType: string | null;
  cards: CardBrief[];
}

export function groupCardsByTimeline(
  cards: CardBrief[],
  timeline: TimelineEvent[],
): TimelineCardGroup[] {
  const sorted = sortCardsByTime(cards);
  const byEvent = new Map<number, CardBrief[]>();
  const noEvent: CardBrief[] = [];

  for (const card of sorted) {
    if (card.event_id != null) {
      const list = byEvent.get(card.event_id) ?? [];
      list.push(card);
      byEvent.set(card.event_id, list);
    } else {
      noEvent.push(card);
    }
  }

  const groups: TimelineCardGroup[] = [];

  for (const ev of timeline) {
    const eventCards = byEvent.get(ev.event_id);
    if (!eventCards?.length) continue;
    groups.push({
      key: `event-${ev.event_id}`,
      event: ev,
      eventDate: ev.event_date,
      eventLabel: ev.event_title,
      eventType: ev.event_type,
      cards: eventCards,
    });
    byEvent.delete(ev.event_id);
  }

  const orphanEvents = [...byEvent.entries()].sort(([, aCards], [, bCards]) => {
    const aDate = aCards[0]?.event_date ?? aCards[0]?.created_at ?? "";
    const bDate = bCards[0]?.event_date ?? bCards[0]?.created_at ?? "";
    return new Date(bDate).getTime() - new Date(aDate).getTime();
  });

  for (const [eventId, eventCards] of orphanEvents) {
    const first = eventCards[0];
    groups.push({
      key: `event-${eventId}`,
      event: null,
      eventDate: first.event_date,
      eventLabel: first.event_title,
      eventType: first.event_type,
      cards: eventCards,
    });
  }

  if (noEvent.length) {
    groups.push({
      key: "ungrouped",
      event: null,
      eventDate: null,
      eventLabel: null,
      eventType: null,
      cards: noEvent,
    });
  }

  return groups;
}

/** Group feed cards by event, newest events first (no company timeline API required). */
export function groupCardsByEvent(cards: CardBrief[]): TimelineCardGroup[] {
  const sorted = sortCardsByTime(cards);
  const byEvent = new Map<number, CardBrief[]>();
  const noEvent: CardBrief[] = [];

  for (const card of sorted) {
    if (card.event_id != null) {
      const list = byEvent.get(card.event_id) ?? [];
      list.push(card);
      byEvent.set(card.event_id, list);
    } else {
      noEvent.push(card);
    }
  }

  const groups: TimelineCardGroup[] = [...byEvent.entries()]
    .sort(([, aCards], [, bCards]) => {
      const aDate = aCards[0]?.event_date ?? aCards[0]?.created_at ?? "";
      const bDate = bCards[0]?.event_date ?? bCards[0]?.created_at ?? "";
      return new Date(bDate).getTime() - new Date(aDate).getTime();
    })
    .map(([eventId, eventCards]) => {
      const first = eventCards[0];
      return {
        key: `event-${eventId}`,
        event: null,
        eventDate: first.event_date,
        eventLabel: first.event_title,
        eventType: first.event_type,
        cards: eventCards,
      };
    });

  if (noEvent.length) {
    groups.push({
      key: "ungrouped",
      event: null,
      eventDate: null,
      eventLabel: "Other updates",
      eventType: null,
      cards: noEvent,
    });
  }

  return groups;
}

const EVENT_TYPE_ORDER: Record<EventType, number> = {
  QUARTERLY_RESULT: 0,
  ANNUAL_REPORT: 1,
  INVESTOR_PRESENTATION: 2,
  CONCALL_TRANSCRIPT: 3,
  PRESS_RELEASE: 4,
  EXCHANGE_FILING: 5,
  SHAREHOLDING_PATTERN: 6,
  CREDIT_RATING: 7,
};

export interface QuarterEventGroup<T extends QuarterTimelineEvent = QuarterTimelineEvent> {
  key: string;
  label: string;
  periodEndDate: string;
  events: T[];
}

/** Minimal shape for quarter grouping (hub `TimelineEvent` and `EventBriefV1`). */
export interface QuarterTimelineEvent {
  event_id: number;
  event_type: EventType;
  event_title: string;
  event_date: string;
  overall_signal?: string | null;
  overall_severity?: string | null;
  summary_text?: string | null;
  period?: PeriodBrief | null;
}

function eventTypeRank(eventType: EventType): number {
  return EVENT_TYPE_ORDER[eventType] ?? 99;
}

function sortEventsWithinQuarter<T extends QuarterTimelineEvent>(events: T[]): T[] {
  return [...events].sort((a, b) => {
    const rankDiff = eventTypeRank(a.event_type) - eventTypeRank(b.event_type);
    if (rankDiff !== 0) return rankDiff;
    const dateDiff = new Date(b.event_date).getTime() - new Date(a.event_date).getTime();
    if (dateDiff !== 0) return dateDiff;
    return b.event_id - a.event_id;
  });
}

function resolveQuarterGroupLabel<T extends QuarterTimelineEvent>(events: T[]): string {
  for (const event of events) {
    if (event.period?.display_label) return event.period.display_label;
  }
  for (const event of events) {
    if (event.period?.fy_label != null && event.period.quarter != null) {
      return `Q${event.period.quarter} ${event.period.fy_label}`;
    }
  }
  for (const event of events) {
    const parsed = eventTitleToPeriodLabel(event.event_title);
    if (parsed) return parsed;
  }
  return resolveQuarterPeriodLabel(null, events[0]?.event_title);
}

/** Group company events by reporting quarter, newest quarter first. */
export function groupEventsByQuarter<T extends QuarterTimelineEvent>(
  events: T[],
): QuarterEventGroup<T>[] {
  const byKey = new Map<string, QuarterEventGroup<T>>();

  for (const event of events) {
    const parsedPeriod = eventTitleToPeriodLabel(event.event_title);
    const key =
      event.period?.period_id != null
        ? `period-${event.period.period_id}`
        : parsedPeriod
          ? `period-${parsedPeriod}`
          : `ungrouped-${event.event_date}`;
    const periodEndDate = event.period?.period_end_date ?? event.event_date;

    let group = byKey.get(key);
    if (!group) {
      group = { key, label: "", periodEndDate, events: [] };
      byKey.set(key, group);
    }
    group.events.push(event);
    if (
      event.period?.period_end_date &&
      new Date(event.period.period_end_date).getTime() >
        new Date(group.periodEndDate).getTime()
    ) {
      group.periodEndDate = event.period.period_end_date;
    }
  }

  const groups = [...byKey.values()];
  for (const group of groups) {
    group.events = sortEventsWithinQuarter(group.events);
    group.label = resolveQuarterGroupLabel(group.events);
  }
  groups.sort(
    (a, b) => new Date(b.periodEndDate).getTime() - new Date(a.periodEndDate).getTime(),
  );
  return groups;
}
