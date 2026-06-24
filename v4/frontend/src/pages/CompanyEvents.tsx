import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { CompanyHub, Signal } from "@/api/types";
import { CompanyEventsTable } from "@/components/company/CompanyEventsTable";
import { PageLoader } from "@/components/common/Spinner";
import { Empty } from "@/components/common/Empty";
import { BackButton } from "@/components/common/BackButton";
import { filterQuarterTimelineEvents, groupEventsByQuarter } from "@/lib/events";

export function CompanyEvents() {
  const { ticker } = useParams<{ ticker: string }>();

  const { data: hub, isLoading: hubLoading } = useQuery({
    queryKey: ["company", ticker],
    queryFn: () => api<CompanyHub>(`/companies/${ticker}`),
    enabled: !!ticker,
  });

  const { data: signals = [] } = useQuery({
    queryKey: ["company-signals", ticker],
    queryFn: () =>
      api<Signal[]>(`/companies/${ticker}/signals`, { query: { limit: 200 } }),
    enabled: !!ticker,
  });

  const timelineEvents = useMemo(
    () => filterQuarterTimelineEvents(hub?.timeline ?? []),
    [hub?.timeline],
  );
  const quarterGroups = useMemo(
    () => groupEventsByQuarter(timelineEvents),
    [timelineEvents],
  );

  if (hubLoading) return <PageLoader />;
  if (!hub || !ticker) return <div className="text-ink-mute">Company not found.</div>;

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <BackButton fallback={`/company/${ticker}`} />

      <div>
        <h1 className="text-xl font-semibold text-ink">Event timeline</h1>
        <p className="text-sm text-ink-mute mt-1">
          <Link to={`/company/${ticker}`} className="hover:text-ink transition-colors">
            {hub.company.name}
          </Link>
          {quarterGroups.length > 0 && (
            <>
              <span className="text-ink-soft/60 mx-1.5">·</span>
              {quarterGroups.length} {quarterGroups.length === 1 ? "quarter" : "quarters"}
              <span className="text-ink-soft/60 mx-1.5">·</span>
              {timelineEvents.length} {timelineEvents.length === 1 ? "event" : "events"}
            </>
          )}
        </p>
      </div>

      {timelineEvents.length === 0 ? (
        <Empty title="No events" />
      ) : (
        <CompanyEventsTable
          quarterGroups={quarterGroups}
          signals={signals}
          ticker={ticker}
          latestEventId={hub.latest_event_id}
        />
      )}
    </div>
  );
}
