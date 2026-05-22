import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, FileText } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type { CardBrief, EventDetailV1, FinancialSnapshotRow, SignalBriefV1 } from "@/api/types";
import { IntelligenceCard } from "@/components/cards/IntelligenceCard";
import { SaveWatchItemDialog } from "@/components/cards/SaveWatchItemDialog";
import { PageLoader } from "@/components/common/Spinner";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import { filterInsightListCards } from "@/lib/cards";
import {
  eventTypeLabel,
  formatCr,
  formatDate,
  formatNumber,
  formatPct,
  mainIssueLabel,
} from "@/lib/format";

const CONCALL_INITIAL_FACTS = 4;

function formatSnapshotValue(row: FinancialSnapshotRow): string {
  if (row.unit === "%") return formatPct(row.current_value);
  if (row.unit === "Cr") return formatCr(row.current_value);
  return formatNumber(row.current_value, row.unit === "Rs" ? 2 : 0);
}

function EventFinancialSnapshot({
  rows,
  periodLabel,
}: {
  rows: FinancialSnapshotRow[];
  periodLabel: string | undefined;
}) {
  if (rows.length === 0) return null;
  return (
    <section className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-line/60">
        <h2 className="text-base font-semibold">Key numbers</h2>
        <p className="text-xs text-ink-soft mt-0.5">
          {periodLabel ? `${periodLabel} vs prior year` : "This period vs prior year"}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-ink-soft">
            <tr>
              <th className="px-5 py-2 text-left font-medium">Metric</th>
              <th className="px-5 py-2 text-right font-medium">Current</th>
              <th className="px-5 py-2 text-right font-medium hidden sm:table-cell">Prior</th>
              <th className="px-5 py-2 text-right font-medium">YoY</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.code} className="border-t border-line/40">
                <td className="px-5 py-2.5 text-ink-mute">{row.metric}</td>
                <td className="px-5 py-2.5 text-right num text-ink font-medium">
                  {formatSnapshotValue(row)}
                </td>
                <td className="px-5 py-2.5 text-right num text-ink-soft hidden sm:table-cell">
                  {row.unit === "%"
                    ? formatPct(row.previous_value)
                    : row.unit === "Cr"
                      ? formatCr(row.previous_value)
                      : formatNumber(row.previous_value, row.unit === "Rs" ? 2 : 0)}
                </td>
                <td
                  className={clsx(
                    "px-5 py-2.5 text-right num font-medium",
                    row.yoy_change_pct != null && row.yoy_change_pct > 0 && "text-positive",
                    row.yoy_change_pct != null && row.yoy_change_pct < 0 && "text-negative",
                  )}
                >
                  {formatPct(row.yoy_change_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function documentIconTitle(d: EventDetailV1["documents"][number]): string {
  return [
    d.document_title,
    d.document_type.replace(/_/g, " ").toLowerCase(),
    d.document_date ? formatDate(d.document_date) : null,
    `${d.values_extracted ?? 0} values extracted`,
    d.extraction_confidence != null
      ? `${d.extraction_confidence.toFixed(0)}% extraction confidence`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function EventDocumentIcons({ documents }: { documents: EventDetailV1["documents"] }) {
  if (documents.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      {documents.map((d) => (
        <Link
          key={d.document_id}
          to={`/documents/${d.document_id}`}
          className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-line/60 bg-surface-2 text-ink-mute hover:text-ink hover:border-line-strong hover:bg-surface transition-colors"
          title={documentIconTitle(d)}
          aria-label={`Open source document: ${d.document_title}`}
        >
          <FileText size={16} strokeWidth={1.75} aria-hidden />
        </Link>
      ))}
    </div>
  );
}

function EventSignalsSection({
  signals,
  symbol,
}: {
  signals: SignalBriefV1[];
  symbol: string | undefined;
}) {
  const navigate = useNavigate();
  if (signals.length === 0) return null;

  return (
    <section className="card p-5">
      <div className="flex items-baseline justify-between gap-2 mb-3">
        <h2 className="text-base font-semibold">Signals from this event</h2>
        {symbol && (
          <button
            type="button"
            onClick={() => navigate("/signals")}
            className="text-xs text-ink-soft hover:text-ink"
          >
            All signals
            <ChevronRight size={14} className="inline" />
          </button>
        )}
      </div>
      <div className="divide-y divide-line/50">
        {signals.map((s) => (
          <button
            key={s.signal_id}
            type="button"
            onClick={() => navigate(`/signals/${s.signal_id}`)}
            className="w-full flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0 text-left hover:bg-surface-2/40 -mx-2 px-2 rounded-lg transition-colors"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium line-clamp-2">{s.headline || s.signal_name}</div>
              <div className="text-xs text-ink-soft mt-0.5 capitalize">
                {s.signal_category.replace(/_/g, " ")}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <SeverityBadge level={s.severity} />
              <SignalBadge direction={s.direction} />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function RelatedEventsSection({
  events,
  symbol,
  currentEventId,
}: {
  events: EventDetailV1["related_events"];
  symbol: string | undefined;
  currentEventId: number;
}) {
  const navigate = useNavigate();
  const others = events.filter((e) => e.event_id !== currentEventId);
  if (others.length === 0 || !symbol) return null;

  return (
    <section className="card p-5">
      <h2 className="text-base font-semibold mb-3">Other events</h2>
      <ul className="space-y-2">
        {others.map((ev) => (
          <li key={ev.event_id}>
            <button
              type="button"
              onClick={() => navigate(`/company/${symbol}/event/${ev.event_id}`)}
              className="w-full text-left card-2 p-3 hover:border-line-strong transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{ev.event_title}</div>
                  <div className="text-[11px] text-ink-soft mt-0.5">
                    {eventTypeLabel(ev.event_type)} · {formatDate(ev.event_date)}
                  </div>
                </div>
                {ev.overall_signal && <SignalBadge direction={ev.overall_signal} />}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ConcernHeatmap({ rows }: { rows: EventDetailV1["concern_heatmap"] }) {
  if (rows.length === 0) return null;
  return (
    <section className="card p-5">
      <h2 className="text-base font-semibold mb-3">Analyst concerns</h2>
      <div className="space-y-2.5">
        {rows.map((row) => (
          <div key={row.topic}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-ink-mute">{row.topic}</span>
              <span className="num text-ink-soft">
                {row.count} · {row.percent}%
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-surface overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-ink-mute to-line-strong rounded-full"
                style={{ width: `${row.percent}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ManagementCommentary({
  facts,
  showAll,
  onToggle,
}: {
  facts: EventDetailV1["concall_facts"];
  showAll: boolean;
  onToggle: () => void;
}) {
  if (facts.length === 0) return null;
  const visible = showAll ? facts : facts.slice(0, CONCALL_INITIAL_FACTS);

  return (
    <section className="card p-5 md:p-6">
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-base font-semibold">Management commentary</h2>
        {facts.length > CONCALL_INITIAL_FACTS && (
          <button type="button" onClick={onToggle} className="text-xs text-ink-soft hover:text-ink">
            {showAll ? "Show fewer" : `All ${facts.length} items`}
          </button>
        )}
      </div>
      <div className="space-y-2">
        {visible.map((f, i) => (
          <div key={i} className="card-2 p-3">
            <div className="flex items-center gap-2 flex-wrap text-[11px] uppercase tracking-wider text-ink-soft mb-1">
              <span>{f.fact_type}</span>
              {f.topic && <span>· {f.topic}</span>}
              {f.target_period && <span>· {f.target_period}</span>}
              {f.direction && <SignalBadge direction={f.direction} />}
            </div>
            <p className="text-sm text-ink leading-relaxed">{f.extracted_claim}</p>
            {f.document_id != null && (
              <p className="text-xs text-ink-soft mt-2 pt-2 border-t border-line/50">
                <span className="text-ink-mute">Source: </span>
                <SourceDocumentLink
                  documentId={f.document_id}
                  page={f.page_number}
                  label={
                    f.document_title
                      ? `${f.document_title}${f.page_number != null ? ` · p.${f.page_number}` : ""}`
                      : "View transcript"
                  }
                />
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function buildCardsEmptyMessage(data: EventDetailV1, publishedCardCount: number): string {
  const st = data.ingestion_status;
  if (st.unpublished_card_count > 0) {
    return `${st.unpublished_card_count} card${st.unpublished_card_count === 1 ? "" : "s"} awaiting review before they appear here.`;
  }
  if (st.values_extracted_total > 0 && publishedCardCount === 0) {
    return "Financial data was extracted but intelligence cards have not been generated yet.";
  }
  if (st.document_count === 0) {
    return "No source documents are linked to this event yet.";
  }
  if (st.published_signal_count > 0) {
    return "Signals fired for this event — published cards will appear here once generated.";
  }
  return "No published cards for this event yet.";
}

export function EventDetailPage() {
  const { symbol, eventId } = useParams<{ symbol: string; eventId: string }>();
  const navigate = useNavigate();
  const [watchItemFor, setWatchItemFor] = useState<CardBrief | null>(null);
  const [showAllConcallFacts, setShowAllConcallFacts] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api<EventDetailV1>(`/v1/events/${eventId}`),
    enabled: !!eventId,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Event not found.</div>;

  const companySymbol =
    symbol || data.company?.nse_symbol || data.company?.bse_code || undefined;

  const cards = filterInsightListCards(data.cards);
  const isConcallEvent = data.event_type === "CONCALL_TRANSCRIPT";
  const showFinancialSnapshot = data.financial_snapshot.length > 0;
  const primaryTitle = data.period?.display_label || data.event_title;
  const typeLabel = eventTypeLabel(data.event_type);
  const cardsEmptyMessage = buildCardsEmptyMessage(
    data,
    data.ingestion_status.published_card_count,
  );
  const summaryText =
    data.summary_text ||
    (data.signals.length > 0
      ? data.signals[0].headline ||
        data.signals[0].explanation ||
        data.signals[0].signal_name
      : null);

  const sidebar = (
    <>
      <ConcernHeatmap rows={data.concern_heatmap} />
      <EventSignalsSection signals={data.signals} symbol={companySymbol} />
      <RelatedEventsSection
        events={data.related_events}
        symbol={companySymbol}
        currentEventId={data.event_id}
      />
    </>
  );

  return (
    <div className="w-full min-w-0 space-y-5">
      <button
        type="button"
        onClick={() => navigate(companySymbol ? `/company/${companySymbol}` : "/")}
        className="btn-ghost -ml-2 text-sm"
      >
        <ArrowLeft size={16} /> Back to {data.company?.company_name || "company"}
      </button>

      <section className="card p-5 md:p-6">
        <div className="min-w-0">
          {typeLabel && (
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">{typeLabel}</div>
          )}
          <div className="flex items-center justify-between gap-3 mt-1 min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <h1 className="text-xl md:text-2xl font-semibold tracking-tight leading-snug min-w-0">
                {primaryTitle}
              </h1>
              <EventDocumentIcons documents={data.documents} />
            </div>
            {data.overall_signal && (
              <div className="shrink-0">
                <SignalBadge direction={data.overall_signal} size="md" />
              </div>
            )}
          </div>
          <p className="text-xs text-ink-soft mt-3">{formatDate(data.event_date)}</p>

          <div className="flex flex-wrap items-center gap-2 mt-4">
            {data.overall_severity && <SeverityBadge level={data.overall_severity} size="md" />}
            {data.overall_confidence !== null && (
              <span
                className="chip-neutral"
                title="Overall confidence for this event synthesis."
              >
                {data.overall_confidence.toFixed(0)}% confidence
              </span>
            )}
          </div>
        </div>

        {summaryText && (
          <div className="mt-5 pt-5 border-t border-line/60">
            <div className="text-xs uppercase tracking-wider text-ink-soft mb-2">Event summary</div>
            <p
              className={clsx(
                "text-[15px] leading-relaxed",
                data.summary_text ? "text-ink" : "text-ink-mute",
              )}
            >
              {summaryText}
            </p>
          </div>
        )}

        {(data.main_issue || data.watch_next) && (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.main_issue && (
              <div className="rounded-xl bg-surface-2 border border-line/60 p-3">
                <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                  {mainIssueLabel(data.overall_signal)}
                </div>
                <div className="text-sm mt-1">{data.main_issue}</div>
              </div>
            )}
            {data.watch_next && (
              <div className="rounded-xl bg-neutral-bg border border-neutral/30 p-3">
                <div className="text-[11px] uppercase tracking-wider text-neutral">Watch next</div>
                <div className="text-sm mt-1">{data.watch_next}</div>
              </div>
            )}
          </div>
        )}
      </section>

      {showFinancialSnapshot && (
        <EventFinancialSnapshot
          rows={data.financial_snapshot}
          periodLabel={data.period?.display_label}
        />
      )}

      {isConcallEvent && data.concall_facts.length > 0 && (
        <ManagementCommentary
          facts={data.concall_facts}
          showAll={showAllConcallFacts}
          onToggle={() => setShowAllConcallFacts((v) => !v)}
        />
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 space-y-5 min-w-0">
          {data.signals.length > 0 && data.event_type !== "QUARTERLY_RESULT" && (
            <EventSignalsSection signals={data.signals} symbol={companySymbol} />
          )}

          <section className="card rounded-xl overflow-hidden">
            <div className="px-4 py-4 border-b border-line/60 bg-surface-2/30">
              <h2 className="text-base font-semibold">Intelligence from this event</h2>
              <p className="text-sm text-ink-mute mt-0.5">
                {cards.length > 0
                  ? "Ordered by materiality — open any card for full detail."
                  : cardsEmptyMessage}
              </p>
            </div>
            {cards.length > 0 && (
              <div className="p-4 space-y-3">
                {cards.map((c) => (
                  <IntelligenceCard
                    key={c.card_id}
                    card={c}
                    showCompany={false}
                    onSaveWatchItem={setWatchItemFor}
                  />
                ))}
              </div>
            )}
          </section>

        </div>

        <div className="space-y-5 min-w-0">{sidebar}</div>
      </div>

      {!isConcallEvent && data.concall_facts.length > 0 && (
        <ManagementCommentary
          facts={data.concall_facts}
          showAll={showAllConcallFacts}
          onToggle={() => setShowAllConcallFacts((v) => !v)}
        />
      )}

      <SaveWatchItemDialog
        open={watchItemFor !== null}
        onClose={() => setWatchItemFor(null)}
        companyId={data.company?.company_id ?? null}
        cardId={watchItemFor?.card_id}
        defaultTitle={watchItemFor ? `Monitor: ${watchItemFor.headline}` : ""}
        defaultDescription={watchItemFor?.watch_next || ""}
      />
    </div>
  );
}
