import type { Company, CompanyEvent, FeedItem, SeverityLevel, Signal, SignalDirection } from "@/api/types";
import { eventTitleToPeriodLabel } from "@/lib/format";

export const OTHER_FILINGS_LABEL = "Other filings";

const EVENT_TYPE_ORDER: Record<string, number> = {
  QUARTERLY_RESULT: 0,
  ANNUAL_REPORT: 1,
  INVESTOR_PRESENTATION: 2,
  CONCALL_TRANSCRIPT: 3,
  EARNINGS_CALL_TRANSCRIPT: 3,
  PRESS_RELEASE: 4,
  EXCHANGE_FILING: 5,
  SHAREHOLDING_PATTERN: 6,
  CREDIT_RATING: 7,
};

export interface TimelineEvent extends CompanyEvent {
  overall_signal?: SignalDirection | null;
  overall_severity?: SeverityLevel | null;
  summary_text?: string | null;
}

export interface QuarterEventGroup<T extends TimelineEvent = TimelineEvent> {
  key: string;
  label: string;
  periodEndDate: string;
  events: T[];
}

function quarterEndIso(fyStart: number, quarter: number): string {
  const qStartMonth = 4 + (quarter - 1) * 3;
  let year = fyStart;
  let endMonth = qStartMonth + 2;
  if (endMonth > 12) {
    endMonth -= 12;
    year += 1;
  }
  const lastDay = new Date(year, endMonth, 0).getDate();
  return `${year}-${String(endMonth).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;
}

function periodEndFromEvent(event: TimelineEvent): string {
  if (event.fiscal_year != null && event.fiscal_quarter != null) {
    return quarterEndIso(event.fiscal_year, event.fiscal_quarter);
  }
  return event.event_date ?? "";
}

function groupKey(event: TimelineEvent): string {
  if (event.period_label) return `period-${event.period_label}`;
  if (event.fiscal_year != null && event.fiscal_quarter != null) {
    return `period-Q${event.fiscal_quarter}-FY${event.fiscal_year}`;
  }
  const parsed = eventTitleToPeriodLabel(event.title);
  if (parsed) return `period-${parsed}`;
  return `ungrouped-${event.event_date ?? event.id}`;
}

function eventTypeRank(eventType: string): number {
  return EVENT_TYPE_ORDER[eventType] ?? 99;
}

function sortEventsWithinQuarter<T extends TimelineEvent>(events: T[]): T[] {
  return [...events].sort((a, b) => {
    const rankDiff = eventTypeRank(a.event_type) - eventTypeRank(b.event_type);
    if (rankDiff !== 0) return rankDiff;
    const dateDiff = new Date(b.event_date ?? 0).getTime() - new Date(a.event_date ?? 0).getTime();
    if (dateDiff !== 0) return dateDiff;
    return b.id.localeCompare(a.id);
  });
}

function resolveQuarterGroupLabel<T extends TimelineEvent>(events: T[]): string {
  for (const event of events) {
    if (event.period_label) return event.period_label;
  }
  for (const event of events) {
    if (event.fiscal_year != null && event.fiscal_quarter != null) {
      const fyEnd = String((event.fiscal_year + 1) % 100).padStart(2, "0");
      return `Q${event.fiscal_quarter} FY${event.fiscal_year}-${fyEnd}`;
    }
  }
  for (const event of events) {
    const parsed = eventTitleToPeriodLabel(event.title);
    if (parsed) return parsed;
  }
  return OTHER_FILINGS_LABEL;
}

/** Whether an event belongs to a fiscal quarter (not the catch-all bucket). */
export function isQuarterGroupedEvent(event: CompanyEvent): boolean {
  if (event.period_label) return true;
  if (event.fiscal_year != null && event.fiscal_quarter != null) return true;
  return eventTitleToPeriodLabel(event.title) != null;
}

/** Drop events that would appear under "Other filings". */
export function filterQuarterTimelineEvents<T extends TimelineEvent>(events: T[]): T[] {
  return events.filter(isQuarterGroupedEvent);
}

/** Group company events by reporting quarter, newest quarter first. */
export function groupEventsByQuarter<T extends TimelineEvent>(
  events: T[],
): QuarterEventGroup<T>[] {
  const byKey = new Map<string, QuarterEventGroup<T>>();

  for (const event of events) {
    const key = groupKey(event);
    const periodEndDate = periodEndFromEvent(event);

    let group = byKey.get(key);
    if (!group) {
      group = { key, label: "", periodEndDate, events: [] };
      byKey.set(key, group);
    }
    group.events.push(event);
    if (
      periodEndDate &&
      new Date(periodEndDate).getTime() > new Date(group.periodEndDate).getTime()
    ) {
      group.periodEndDate = periodEndDate;
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

/** Attach the strongest signal per event for timeline badges. */
export function enrichTimelineEvents(
  events: CompanyEvent[],
  signals: Signal[],
): TimelineEvent[] {
  const byEvent = new Map<string, Signal>();
  for (const signal of signals) {
    if (!signal.event_id || byEvent.has(signal.event_id)) continue;
    byEvent.set(signal.event_id, signal);
  }

  return events.map((event) => {
    const signal = byEvent.get(event.id);
    if (!signal) return event;
    return {
      ...event,
      overall_signal: signal.direction,
      overall_severity: signal.severity,
      summary_text: signal.title ?? signal.description,
    };
  });
}

export interface FeedTimelineEvent extends TimelineEvent {
  signals: Signal[];
}

export interface CompanyFeedGroup {
  company: Company;
  signals: Signal[];
  filingCount: number;
  quarterGroups: QuarterEventGroup<FeedTimelineEvent>[];
  latestDetectedAt: string;
}

/** Group feed signals by company, then quarter/event for the home timeline. */
export function buildCompanyFeedGroups(signals: Signal[]): CompanyFeedGroup[] {
  const byCompany = new Map<string, { company: Company; signals: Signal[] }>();

  for (const signal of signals) {
    const company = signal.company;
    if (!company?.id) continue;
    let group = byCompany.get(company.id);
    if (!group) {
      group = { company, signals: [] };
      byCompany.set(company.id, group);
    }
    group.signals.push(signal);
  }

  const groups: CompanyFeedGroup[] = [];

  for (const { company, signals: companySignals } of byCompany.values()) {
    const byEvent = new Map<string, FeedTimelineEvent>();
    const ungrouped: FeedTimelineEvent[] = [];

    for (const signal of companySignals) {
      const event = signal.event;
      const eventId = event?.id ?? signal.event_id;
      if (eventId) {
        let entry = byEvent.get(eventId);
        if (!entry) {
          entry = event
            ? { ...event, signals: [] }
            : {
                id: eventId,
                company_id: signal.company_id,
                event_type: "QUARTERLY_RESULT",
                event_type_raw: null,
                event_date: signal.detected_at,
                fiscal_year: null,
                fiscal_quarter: null,
                period_label: null,
                title: null,
                source_url: null,
                document_id: null,
                status: null,
                signals: [],
              };
          byEvent.set(eventId, entry);
        }
        entry.signals.push(signal);
      } else {
        ungrouped.push({
          id: signal.id,
          company_id: signal.company_id,
          event_type: "EXCHANGE_FILING",
          event_type_raw: null,
          event_date: signal.detected_at,
          fiscal_year: null,
          fiscal_quarter: null,
          period_label: null,
          title: signal.signal_name || signal.title,
          source_url: null,
          document_id: null,
          status: null,
          signals: [signal],
        });
      }
    }

    for (const entry of byEvent.values()) {
      entry.signals.sort(
        (a, b) =>
          new Date(b.detected_at ?? 0).getTime() - new Date(a.detected_at ?? 0).getTime(),
      );
      const lead = entry.signals[0];
      entry.overall_signal = lead.direction;
      entry.overall_severity = lead.severity;
      entry.summary_text = lead.title ?? lead.description;
    }

    const quarterGroups = groupEventsByQuarter([
      ...filterQuarterTimelineEvents([...byEvent.values()]),
      ...ungrouped,
    ]);

    const latestDetectedAt = companySignals.reduce((latest, s) => {
      const at = s.detected_at ?? "";
      return at > latest ? at : latest;
    }, "");

    groups.push({
      company,
      signals: companySignals,
      filingCount: byEvent.size + ungrouped.length,
      quarterGroups,
      latestDetectedAt,
    });
  }

  groups.sort(
    (a, b) => new Date(b.latestDetectedAt).getTime() - new Date(a.latestDetectedAt).getTime(),
  );
  return groups;
}

/** Group the authenticated event-based home feed by company and reporting period. */
export function buildCompanyFeedGroupsFromItems(items: FeedItem[]): CompanyFeedGroup[] {
  const byCompany = new Map<string, { company: Company; events: FeedTimelineEvent[] }>();
  for (const item of items) {
    let group = byCompany.get(item.company.id);
    if (!group) {
      group = { company: item.company, events: [] };
      byCompany.set(item.company.id, group);
    }
    const signals = [...item.signals].sort(
      (a, b) => new Date(b.detected_at ?? 0).getTime() - new Date(a.detected_at ?? 0).getTime(),
    );
    const lead = signals[0];
    group.events.push({
      ...item.event,
      signals,
      overall_signal: lead?.direction ?? null,
      overall_severity: lead?.severity ?? null,
      summary_text: lead?.title ?? lead?.description ?? null,
    });
  }

  return [...byCompany.values()]
    .map(({ company, events }) => {
      const signals = events.flatMap((event) => event.signals);
      const latestDetectedAt = events.reduce(
        (latest, event) => (event.event_date ?? "") > latest ? (event.event_date ?? "") : latest,
        "",
      );
      return {
        company,
        signals,
        filingCount: events.length,
        quarterGroups: groupEventsByQuarter(events),
        latestDetectedAt,
      };
    })
    .sort(
      (a, b) => new Date(b.latestDetectedAt).getTime() - new Date(a.latestDetectedAt).getTime(),
    );
}

/** Build a single company's feed group from hub data (timeline + signals). */
export function buildCompanyFeedGroupFromHub(
  company: Company,
  timeline: CompanyEvent[],
  signals: Signal[],
): CompanyFeedGroup | null {
  const byEvent = new Map<string, FeedTimelineEvent>();

  for (const event of timeline) {
    if (!isQuarterGroupedEvent(event)) continue;
    byEvent.set(event.id, { ...event, signals: [] });
  }

  for (const signal of signals) {
    const event = signal.event ?? (signal.event_id ? byEvent.get(signal.event_id) : null);
    const eventId = event?.id ?? signal.event_id;
    if (!eventId) continue;
    let entry = byEvent.get(eventId);
    if (!entry) {
      entry = event
        ? { ...event, signals: [] }
        : {
            id: eventId,
            company_id: signal.company_id,
            event_type: "QUARTERLY_RESULT",
            event_type_raw: null,
            event_date: signal.detected_at,
            fiscal_year: null,
            fiscal_quarter: null,
            period_label: null,
            title: null,
            source_url: null,
            document_id: null,
            status: null,
            signals: [],
          };
      byEvent.set(eventId, entry);
    }
    entry.signals.push({ ...signal, company, event: entry });
  }

  for (const entry of byEvent.values()) {
    entry.signals.sort(
      (a, b) => new Date(b.detected_at ?? 0).getTime() - new Date(a.detected_at ?? 0).getTime(),
    );
    const lead = entry.signals[0];
    if (!lead) continue;
    entry.overall_signal = lead.direction;
    entry.overall_severity = lead.severity;
    entry.summary_text = lead.title ?? lead.description;
  }

  const events = [...byEvent.values()];
  if (events.length === 0) return null;
  const latestDetectedAt =
    signals.reduce((latest, s) => {
      const at = s.detected_at ?? "";
      return at > latest ? at : latest;
    }, "") || events[0]?.event_date || "";

  return {
    company,
    signals,
    filingCount: events.length,
    quarterGroups: groupEventsByQuarter(events),
    latestDetectedAt,
  };
}
