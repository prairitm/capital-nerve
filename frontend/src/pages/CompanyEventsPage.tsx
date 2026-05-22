import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type { CompanyDetail } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { eventTypeLabel, formatDate } from "@/lib/format";

export function CompanyEventsPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["company", symbol],
    queryFn: () => api<CompanyDetail>(`/v1/companies/${symbol}`),
    enabled: !!symbol,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Company not found.</div>;

  const companyPath = `/company/${symbol}`;
  const timelineLatestEventId = data.timeline[0]?.event_id ?? null;

  return (
    <div className="w-full min-w-0 space-y-5">
      <button
        type="button"
        onClick={() => navigate(companyPath)}
        className="btn-ghost -ml-2 text-sm"
      >
        <ArrowLeft size={16} /> Back to {data.company.short_name || data.company.company_name}
      </button>

      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Event timeline</h1>
        <p className="text-sm text-ink-mute mt-1">
          {data.company.company_name}
          {data.timeline.length > 0 && ` · ${data.timeline.length} events`}
        </p>
      </div>

      {data.timeline.length === 0 ? (
        <div className="card p-8 text-sm text-ink-mute text-center">No events recorded yet.</div>
      ) : (
        <section className="card p-5 md:p-6">
          <ol className="relative border-l border-line ml-2">
            {data.timeline.map((ev) => {
              const isLatest = ev.event_id === timelineLatestEventId;
              const typeLabel = eventTypeLabel(ev.event_type);
              return (
                <li key={ev.event_id} className="ml-4 mb-4 last:mb-0">
                  <span className={clsx("ui-dot", isLatest && "bg-brand ring-2 ring-brand/30")} />
                  <button
                    type="button"
                    onClick={() => navigate(`/company/${symbol}/event/${ev.event_id}`)}
                    className={clsx(
                      "w-full text-left rounded-lg -mx-2 px-2 py-1 transition-colors",
                      isLatest ? "bg-surface-2/60" : "hover:bg-surface-2/40",
                    )}
                  >
                    <span className="text-[11px] uppercase tracking-wider text-ink-soft">
                      {formatDate(ev.event_date)}
                      {typeLabel && <> · {typeLabel}</>}
                    </span>
                    <div className="font-medium mt-1">{ev.event_title}</div>
                    {(ev.overall_signal || ev.overall_severity) && (
                      <div className="flex items-center gap-2 mt-1.5">
                        {ev.overall_signal && <SignalBadge direction={ev.overall_signal} />}
                        {ev.overall_severity && <SeverityBadge level={ev.overall_severity} />}
                      </div>
                    )}
                    {ev.summary_text && (
                      <p className="text-xs text-ink-mute mt-2">{ev.summary_text}</p>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </div>
  );
}
