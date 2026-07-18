import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "@/api/client";
import type { FeedItem, FeedSummary } from "@/api/types";
import { FeedCompanyTimeline } from "@/components/feed/FeedCompanyTimeline";
import { Empty } from "@/components/common/Empty";
import { ErrorState, PageHeader, PageSkeleton, StatusSummary } from "@/components/common/DashboardUI";
import { buildCompanyFeedGroupsFromItems } from "@/lib/events";

const severityRank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 } as const;

export function HomeFeed() {
  const feedQuery = useQuery({
    queryKey: ["feed"],
    queryFn: () => api<FeedItem[]>("/feed", { query: { limit: 60 } }),
    refetchInterval: 60_000,
  });
  const summaryQuery = useQuery({
    queryKey: ["feed-summary"],
    queryFn: () => api<FeedSummary>("/feed/summary"),
    refetchInterval: 60_000,
  });
  const items = feedQuery.data;

  const companyGroups = useMemo(
    () => (items ? buildCompanyFeedGroupsFromItems(items).sort((a, b) => {
      const rank = (group: typeof a) => Math.max(0, ...group.signals.map((s) => severityRank[s.severity as keyof typeof severityRank] ?? 0));
      return rank(b) - rank(a);
    }) : []),
    [items],
  );

  if (feedQuery.isLoading || summaryQuery.isLoading) return <PageSkeleton />;
  if (feedQuery.isError || summaryQuery.isError) return <ErrorState onRetry={() => { void feedQuery.refetch(); void summaryQuery.refetch(); }} />;

  const summary = summaryQuery.data;
  const representedCompanies = new Set((items ?? []).map((item) => item.company.id)).size;
  const highPriority = (summary?.by_severity.CRITICAL ?? 0) + (summary?.by_severity.HIGH ?? 0);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader eyebrow="Research monitor" title="Market intelligence" description="Material developments across your company coverage, prioritised by severity." />

      {summary && summary.total > 0 && (
        <StatusSummary items={[
          { label: "Processed filings", value: summary.processed_filings, hint: "Across your watchlist" },
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

      {!items || items.length === 0 ? (
        <Empty
          title="No watched filings yet"
          description="Add companies to your watchlist to see their processed filings here."
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
