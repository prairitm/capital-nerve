import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "@/api/client";
import type { Signal } from "@/api/types";
import { FeedCompanyTimeline } from "@/components/feed/FeedCompanyTimeline";
import { PageLoader } from "@/components/common/Spinner";
import { Empty } from "@/components/common/Empty";
import { buildCompanyFeedGroups } from "@/lib/events";

export function HomeFeed() {
  const { data: signals, isLoading } = useQuery({
    queryKey: ["feed"],
    queryFn: () => api<Signal[]>("/feed", { query: { limit: 60 } }),
  });

  const companyGroups = useMemo(
    () => (signals ? buildCompanyFeedGroups(signals) : []),
    [signals],
  );

  if (isLoading) return <PageLoader />;

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-ink">Latest intelligence</h1>
        <p className="text-sm text-ink-mute mt-0.5">
          Signals grouped by company and reporting period — newest first.
        </p>
      </div>

      {!signals || signals.length === 0 ? (
        <Empty
          title="No signals yet"
          description="Process a financial result through the v3 pipeline and fired signals will appear here."
        />
      ) : (
        <div className="space-y-4">
          {companyGroups.map((group) => (
            <FeedCompanyTimeline key={group.company.id} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}
