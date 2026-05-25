import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "@/api/client";
import type { CompanyDetail, EventBriefV1 } from "@/api/types";
import { CompanyQuarterTimeline } from "@/components/common/CompanyQuarterTimeline";
import { PageLoader } from "@/components/common/Spinner";
import { groupEventsByQuarter } from "@/lib/cards";

export function CompanyEventsPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();

  const { data, isLoading: hubLoading } = useQuery({
    queryKey: ["company", symbol],
    queryFn: () => api<CompanyDetail>(`/v1/companies/${symbol}`),
    enabled: !!symbol,
  });

  const { data: timeline, isLoading: timelineLoading } = useQuery({
    queryKey: ["company", symbol, "events"],
    queryFn: () =>
      api<EventBriefV1[]>(`/v1/companies/${symbol}/events`, {
        query: { limit: 200, dedupe_periods: false },
      }),
    enabled: !!symbol,
  });

  const events = timeline ?? [];
  const quarterGroups = useMemo(() => groupEventsByQuarter(events), [events]);

  if (hubLoading || timelineLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Company not found.</div>;

  const timelineLatestEventId = data.latest_event_id ?? events[0]?.event_id ?? null;

  const companyPath = `/company/${symbol}`;

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
          {quarterGroups.length > 0 &&
            ` · ${quarterGroups.length} ${quarterGroups.length === 1 ? "quarter" : "quarters"} · ${events.length} events`}
        </p>
      </div>

      {events.length === 0 ? (
        <div className="card p-8 text-sm text-ink-mute text-center">No events recorded yet.</div>
      ) : (
        <section className="card p-5 md:p-6">
          {symbol && (
            <CompanyQuarterTimeline
              events={events}
              symbol={symbol}
              latestEventId={timelineLatestEventId}
            />
          )}
        </section>
      )}
    </div>
  );
}
