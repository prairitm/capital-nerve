import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "@/api/client";
import type { FeedSummary, Signal } from "@/api/types";
import { FeedCompanyTimeline } from "@/components/feed/FeedCompanyTimeline";
import { Empty } from "@/components/common/Empty";
import { ErrorState, PageHeader, PageSkeleton, StatusSummary } from "@/components/common/DashboardUI";
import { buildCompanyFeedGroups } from "@/lib/events";

const severityRank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 } as const;

export function HomeFeed() {
  const feedQuery = useQuery({
    queryKey: ["feed"],
    queryFn: () => api<Signal[]>("/feed", { query: { limit: 60 } }),
  });
  const summaryQuery = useQuery({
    queryKey: ["feed-summary"],
    queryFn: () => api<FeedSummary>("/feed/summary"),
  });
  const signals = feedQuery.data;

  const companyGroups = useMemo(
    () => (signals ? buildCompanyFeedGroups(signals).sort((a, b) => {
      const rank = (group: typeof a) => Math.max(0, ...group.signals.map((s) => severityRank[s.severity as keyof typeof severityRank] ?? 0));
      return rank(b) - rank(a);
    }) : []),
    [signals],
  );

  if (feedQuery.isLoading || summaryQuery.isLoading) return <PageSkeleton />;
  if (feedQuery.isError || summaryQuery.isError) return <ErrorState onRetry={() => { void feedQuery.refetch(); void summaryQuery.refetch(); }} />;

  const summary = summaryQuery.data;
  const representedCompanies = new Set((signals ?? []).map((s) => s.company_id).filter(Boolean)).size;
  const highPriority = (summary?.by_severity.CRITICAL ?? 0) + (summary?.by_severity.HIGH ?? 0);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader eyebrow="Research monitor" title="Market intelligence" description="Material developments across your company coverage, prioritised by severity." />

      {summary && summary.total > 0 && (
        <StatusSummary items={[
          { label: "Total signals", value: summary.total, hint: "Across all processed reports" },
          { label: "High priority", value: highPriority, hint: "Critical and high materiality", tone: highPriority ? "warning" : "default" },
          { label: "Coverage", value: representedCompanies, hint: "Companies represented" },
          { label: "Direction", value: `${summary.positive} / ${summary.negative}`, hint: "Positive / negative", tone: summary.negative > summary.positive ? "negative" : "positive" },
        ]} />
      )}

      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">Priority activity</h2>
          <p className="mt-0.5 text-xs text-ink-mute">Higher-materiality companies appear first.</p>
        </div>
      </div>

      {!signals || signals.length === 0 ? (
        <Empty
          title="No signals yet"
          description="No material intelligence is available for the current coverage universe."
        />
      ) : (
        <div className="space-y-3">
          {companyGroups.map((group) => (
            <FeedCompanyTimeline key={group.company.id} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}
