import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  FileBarChart,
  MessageCircle,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { api } from "@/api/client";
import type { CardBrief, FeedSummary, IntelligenceObjectBrief } from "@/api/types";
import { IntelligenceTimeline } from "@/components/cards/IntelligenceTimeline";
import { SaveWatchItemDialog } from "@/components/cards/SaveWatchItemDialog";
import { PageLoader } from "@/components/common/Spinner";
import { Empty } from "@/components/common/Empty";
import clsx from "clsx";
import {
  filterHomeFeedCards,
  groupCardsByEvent,
  intelligenceObjectBriefToCardBrief,
} from "@/lib/cards";
const FEED_TABS = [
  { value: "all", label: "All" },
  { value: "watchlist", label: "Watchlist" },
  { value: "results", label: "Results" },
] as const;

type FeedTabValue = (typeof FEED_TABS)[number]["value"];

type WatchlistPulseFilter = "red_flags" | "negative" | "positive" | "margin_pressure" | "management";
type ResultsPulseFilter = "verdicts" | "growth" | "margins" | "risks";
type PulseFilter = WatchlistPulseFilter | ResultsPulseFilter;

type TabValue = FeedTabValue | PulseFilter;

const TAB_COPY: Record<TabValue, { heading: string; blurb: string }> = {
  all: {
    heading: "Today's intelligence",
    blurb: "Latest cards first — sorted by event date, newest at the top.",
  },
  watchlist: {
    heading: "Watchlist updates",
    blurb: "Only companies you're tracking — newest material changes first.",
  },
  results: {
    heading: "Earnings & results",
    blurb: "Quarterly result verdicts and financial movement cards.",
  },
  red_flags: {
    heading: "Red flags",
    blurb: "Risks, deterioration, and items that may need immediate review.",
  },
  negative: {
    heading: "Negative signals",
    blurb: "Deterioration and cautionary cards across your watchlist.",
  },
  positive: {
    heading: "Constructive signals",
    blurb: "Growth, margin improvement, and constructive signals.",
  },
  margin_pressure: {
    heading: "Margin pressure",
    blurb: "Negative margin movement cards worth a closer look.",
  },
  management: {
    heading: "Management & guidance",
    blurb: "Tone, guidance changes, and what leadership said on calls.",
  },
  verdicts: {
    heading: "Result verdicts",
    blurb: "Headline quarterly reads and overall result assessments.",
  },
  growth: {
    heading: "Revenue growth",
    blurb: "Top-line growth and revenue movement cards.",
  },
  margins: {
    heading: "Margin movement",
    blurb: "EBITDA and margin trajectory cards from recent results.",
  },
  risks: {
    heading: "Result risks",
    blurb: "Red flags, profit quality, and expense pressure from earnings.",
  },
};

function resolveApiTab(feedScope: FeedTabValue, pulseFilter: PulseFilter | null): string {
  if (pulseFilter) return pulseFilter;
  if (feedScope === "results") return "results";
  return "all";
}

export function HomePage() {
  const [feedScope, setFeedScope] = useState<FeedTabValue>("all");
  const [pulseFilter, setPulseFilter] = useState<PulseFilter | null>(null);
  const [watchItemFor, setWatchItemFor] = useState<CardBrief | null>(null);

  const viewTab: TabValue = pulseFilter ?? feedScope;

  const summaryQ = useQuery({
    queryKey: ["feedSummary"],
    queryFn: () => api<FeedSummary>("/v1/intelligence-objects/summary"),
  });
  const cardsQ = useQuery({
    queryKey: ["feed", feedScope, pulseFilter],
    queryFn: () =>
      api<IntelligenceObjectBrief[]>("/v1/intelligence-objects", {
        query: {
          feed: feedScope === "watchlist" ? "watchlist" : "home",
          tab: resolveApiTab(feedScope, pulseFilter),
          limit: 40,
        },
      }),
  });
  const timelineGroups = useMemo(() => {
    if (!cardsQ.data) return [];
    const cards = cardsQ.data.map(intelligenceObjectBriefToCardBrief);
    return groupCardsByEvent(
      filterHomeFeedCards(cards, resolveApiTab(feedScope, pulseFilter)),
    );
  }, [cardsQ.data, feedScope, pulseFilter]);
  const cardCount = useMemo(
    () => timelineGroups.reduce((n, g) => n + g.cards.length, 0),
    [timelineGroups],
  );
  const tabCopy = TAB_COPY[viewTab];

  const handleFeedScopeChange = (scope: FeedTabValue) => {
    setFeedScope(scope);
    setPulseFilter(null);
  };

  return (
    <div className="w-full min-w-0 space-y-5">
      <header>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Market Intelligence</h1>
        <p className="text-sm text-ink-mute mt-1">
          Company events surfaced as cards — scan newest first, open for evidence and detail.
        </p>
      </header>

      <SummaryBar
        summary={summaryQ.data}
        feedScope={feedScope}
        pulseFilter={pulseFilter}
        onFeedScopeChange={handleFeedScopeChange}
        onPulseFilterChange={setPulseFilter}
      />

      <section className="card rounded-xl overflow-hidden">
        <div className="px-4 py-4 border-b border-line/60 bg-surface-2/30">
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-base font-semibold">{tabCopy.heading}</h2>
              <p className="text-sm text-ink-mute mt-0.5">{tabCopy.blurb}</p>
            </div>
            {cardCount > 0 && (
              <span className="text-xs text-ink-soft shrink-0">
                {cardCount} {cardCount === 1 ? "card" : "cards"}
              </span>
            )}
          </div>
        </div>

        <div className="p-4">
          {cardsQ.isLoading ? (
            <PageLoader />
          ) : timelineGroups.length === 0 ? (
            <Empty
              title="Nothing in this view yet"
              description={
                feedScope === "all"
                  ? "No pipeline signals have fired yet for published events — upload filings and check back after extraction, or open Results for verdict cards."
                  : feedScope === "results"
                    ? "Try another Pulse filter above, or upload a quarterly result filing."
                    : "Try another Pulse filter above, or add companies to your watchlist."
              }
              icon={<FileBarChart size={36} />}
            />
          ) : (
            <IntelligenceTimeline
              groups={timelineGroups}
              onSaveWatchItem={setWatchItemFor}
              showCompanyInHeader
            />
          )}
        </div>
      </section>

      <SaveWatchItemDialog
        open={watchItemFor !== null}
        onClose={() => setWatchItemFor(null)}
        companyId={watchItemFor?.company.company_id ?? null}
        cardId={watchItemFor?.card_id}
        defaultTitle={watchItemFor ? `Monitor: ${watchItemFor.headline}` : ""}
        defaultDescription={watchItemFor?.watch_next || ""}
      />
    </div>
  );
}

type PulseItem = {
  key: PulseFilter;
  label: string;
  value: number;
  tone?: string;
  icon: typeof FileBarChart;
};

const WATCHLIST_PULSE: (s: FeedSummary | undefined) => PulseItem[] = (summary) => [
  { key: "red_flags", label: "Red flags", value: summary?.red_flags ?? 0, tone: "text-negative", icon: AlertOctagon },
  { key: "negative", label: "Negative", value: summary?.negative_signals ?? 0, tone: "text-negative", icon: TrendingDown },
  { key: "positive", label: "Constructive", value: summary?.positive_signals ?? 0, tone: "text-positive", icon: CheckCircle2 },
  { key: "margin_pressure", label: "Margin pressure", value: summary?.margin_warnings ?? 0, tone: "text-mixed", icon: AlertTriangle },
  { key: "management", label: "Guidance", value: summary?.guidance_updates ?? 0, icon: MessageCircle },
];

const RESULTS_PULSE: (s: FeedSummary | undefined) => PulseItem[] = (summary) => [
  { key: "verdicts", label: "Verdicts", value: summary?.verdicts ?? 0, icon: FileBarChart },
  { key: "growth", label: "Growth", value: summary?.growth ?? 0, tone: "text-positive", icon: TrendingUp },
  { key: "margins", label: "Margins", value: summary?.margins ?? 0, tone: "text-mixed", icon: AlertTriangle },
  { key: "risks", label: "Risks", value: summary?.risks ?? 0, tone: "text-negative", icon: AlertOctagon },
];

function SummaryBar({
  summary,
  feedScope,
  pulseFilter,
  onFeedScopeChange,
  onPulseFilterChange,
}: {
  summary: FeedSummary | undefined;
  feedScope: FeedTabValue;
  pulseFilter: PulseFilter | null;
  onFeedScopeChange: (scope: FeedTabValue) => void;
  onPulseFilterChange: (filter: PulseFilter | null) => void;
}) {
  const showPulse = feedScope !== "all";
  const pulseItems =
    feedScope === "results" ? RESULTS_PULSE(summary) : WATCHLIST_PULSE(summary);

  return (
    <div className={clsx("card rounded-xl px-4 py-3", showPulse && "space-y-3")}>
      <div
        className="flex gap-1 overflow-x-auto -mx-1 px-1 scrollbar-none"
        role="tablist"
        aria-label="Feed scope"
      >
        {FEED_TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={feedScope === t.value}
            onClick={() => onFeedScopeChange(t.value)}
            className={clsx(
              "px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors",
              feedScope === t.value
                ? "btn-brand-active"
                : "text-ink-mute hover:text-ink hover:bg-surface",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {showPulse && (
        <div className="flex flex-wrap items-center gap-x-1 gap-y-2 text-sm border-t border-line/50 pt-3">
          <span className="text-xs uppercase tracking-wider text-ink-soft mr-2 w-full sm:w-auto">Pulse</span>
          {pulseItems.map((it, i) => (
            <span key={it.label} className="inline-flex items-center">
              {i > 0 && <span className="text-line mx-2 hidden sm:inline">|</span>}
              <button
                type="button"
                onClick={() => onPulseFilterChange(pulseFilter === it.key ? null : it.key)}
                className={clsx(
                  "inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 -mx-1.5 transition-colors hover:bg-surface-2 cursor-pointer",
                  pulseFilter === it.key && "bg-surface-2 ring-1 ring-line/80",
                )}
              >
                <it.icon size={14} className={it.tone ?? "text-ink-soft"} />
                <span className="num font-semibold text-ink">{it.value}</span>
                <span className="text-ink-mute text-xs">{it.label}</span>
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
