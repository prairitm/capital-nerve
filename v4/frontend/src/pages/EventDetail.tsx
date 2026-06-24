import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { api } from "@/api/client";
import type { EventDetail as EventDetailT, ExtractedValue } from "@/api/types";
import { EventSignalList } from "@/components/signals/EventSignalList";
import { PageLoader } from "@/components/common/Spinner";
import { Empty } from "@/components/common/Empty";
import { BackButton } from "@/components/common/BackButton";
import { basisLabel, eventTypeLabel, formatDate, formatMetricValue } from "@/lib/format";
import { FactSourceLink } from "@/components/common/FactSourceLink";

function FactLineItem({ fact }: { fact: ExtractedValue }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-ink-mute">{fact.value_name}</span>
      {fact.basis && (
        <span className="chip-neutral text-[10px] shrink-0">{basisLabel(fact.basis)}</span>
      )}
    </div>
  );
}

export function EventDetail() {
  const { ticker, eventId } = useParams<{ ticker: string; eventId: string }>();

  const { data, isLoading } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api<EventDetailT>(`/events/${eventId}`),
    enabled: !!eventId,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Event not found.</div>;

  const { event, company, facts, metrics, signals } = data;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <BackButton fallback={ticker ? `/company/${ticker}` : "/companies"} />

      <header className="card p-5 space-y-2">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
            {eventTypeLabel(event.event_type)}
          </span>
          {event.period_label && <span className="chip-neutral">{event.period_label}</span>}
        </div>
        <h1 className="text-xl font-semibold text-ink leading-snug">
          {company?.name}
          {event.period_label && (
            <span className="text-ink-mute font-normal"> · {event.period_label}</span>
          )}
        </h1>
        <div className="text-sm text-ink-soft">{formatDate(event.event_date)}</div>
        {event.document_id && (
          <Link
            to={`/documents/${event.document_id}`}
            className="inline-flex items-center gap-1.5 text-sm text-ink-mute hover:text-ink"
          >
            <FileText size={14} /> View source document
          </Link>
        )}
      </header>

      <EventSignalList signals={signals} metrics={metrics} />

      {/* Metrics */}
      {metrics.length > 0 && (
        <section className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-line/60">
            <h2 className="text-base font-semibold">Computed metrics</h2>
          </div>
          <div className="md:hidden divide-y divide-line/40">
            {metrics.map((m) => (
              <div
                key={m.metric_code}
                className="px-5 py-3 flex items-center justify-between gap-4"
              >
                <span className="text-ink-mute min-w-0">{m.metric_name}</span>
                <span className="num text-ink font-medium whitespace-nowrap shrink-0">
                  {formatMetricValue(m.metric_value, m.unit)}
                </span>
              </div>
            ))}
          </div>
          <table className="hidden md:table w-full text-sm">
            <tbody>
              {metrics.map((m) => (
                <tr key={m.metric_code} className="border-t border-line/40 first:border-t-0">
                  <td className="px-5 py-2.5 text-ink-mute">{m.metric_name}</td>
                  <td className="px-5 py-2.5 text-right num text-ink font-medium">
                    {formatMetricValue(m.metric_value, m.unit)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Extracted facts */}
      {facts.length > 0 ? (
        <section className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-line/60">
            <h2 className="text-base font-semibold">Extracted facts</h2>
            <p className="text-xs text-ink-soft mt-0.5">Values pulled from the filing.</p>
          </div>
          <div className="md:hidden divide-y divide-line/40">
            {facts.map((f) => (
              <div key={`${f.value_code}-${f.basis}`} className="px-5 py-3.5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <FactLineItem fact={f} />
                  </div>
                  <div className="num text-ink font-medium whitespace-nowrap shrink-0">
                    {formatMetricValue(f.value_numeric, f.unit)}
                  </div>
                </div>
                <div className="mt-2 text-ink-soft text-xs">
                  <FactSourceLink documentId={event.document_id} fact={f} />
                </div>
              </div>
            ))}
          </div>
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
                <tr>
                  <th className="px-5 py-2 text-left font-medium">Line item</th>
                  <th className="px-5 py-2 text-right font-medium">Value</th>
                  <th className="px-5 py-2 text-left font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {facts.map((f) => (
                  <tr key={`${f.value_code}-${f.basis}`} className="border-t border-line/40 align-top">
                    <td className="px-5 py-2.5">
                      <FactLineItem fact={f} />
                    </td>
                    <td className="px-5 py-2.5 text-right num text-ink font-medium whitespace-nowrap">
                      {formatMetricValue(f.value_numeric, f.unit)}
                    </td>
                    <td className="px-5 py-2.5 text-ink-soft text-xs max-w-md">
                      <FactSourceLink documentId={event.document_id} fact={f} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <Empty
          title="No extracted facts"
          description="This event has not been processed by the pipeline."
        />
      )}
    </div>
  );
}
