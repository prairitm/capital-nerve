import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import clsx from "clsx";
import { api } from "@/api/client";
import type {
  ReviewItem,
  ReviewPipelineDetail,
  ReviewPipelineExtracted,
  ReviewPipelineFact,
  ReviewPipelineMetric,
  SignalSkip,
} from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { formatCr, formatNumber, formatPct } from "@/lib/format";
import { useAuthStore } from "@/store/auth";
import { Navigate } from "react-router-dom";

const SKIP_REASON_LABELS: Record<string, string> = {
  no_numeric_rule: "Not a metric rule",
  metric_missing: "Metric not calculated",
  metric_value_missing: "Metric has no value",
  threshold_not_met: "Threshold not met",
};

function stageLabel(key: string): string {
  const labels: Record<string, string> = {
    pages: "Pages",
    extracted: "Extracted",
    facts: "Facts",
    metrics: "Metrics",
    signals: "Signals",
    cards: "Cards",
    supplemental_order_book: "Order book",
  };
  return labels[key] ?? key;
}

function skipReasonLabel(skip: SignalSkip): string {
  return SKIP_REASON_LABELS[skip.reason] ?? skip.reason.replace(/_/g, " ");
}

function formatPipelineValue(value: number | string | null, unit: string | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  const u = (unit ?? "").toLowerCase();
  if (u === "%" || unit === "%") return formatPct(value, 1);
  if (u === "rs" || unit === "Rs") return `₹${formatNumber(value, 2)}`;
  if (u === "crore" || u === "cr" || !unit) return formatCr(value);
  return `${formatNumber(value, value < 100 ? 2 : 0)} ${unit}`;
}

function PipelineStages({ stages }: { stages: Record<string, number> }) {
  const order = ["pages", "extracted", "facts", "metrics", "signals", "cards"];
  const keys = order.filter((k) => stages[k] !== undefined);
  if (keys.length === 0) return <span className="text-ink-soft">Pipeline not run yet</span>;
  return (
    <div className="flex flex-wrap gap-2">
      {keys.map((k) => (
        <span
          key={k}
          className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-2 py-0.5 text-xs text-ink-mute"
        >
          <span className="text-ink-soft">{stageLabel(k)}</span>
          <span className="num font-medium text-ink">{stages[k]}</span>
        </span>
      ))}
    </div>
  );
}

function DataTable({
  headers,
  rows,
  empty,
}: {
  headers: string[];
  rows: React.ReactNode[][];
  empty: string;
}) {
  if (rows.length === 0) {
    return <p className="text-xs text-ink-soft">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-line/40">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-line/40 bg-surface-2/80 text-left text-ink-soft">
            {headers.map((h) => (
              <th key={h} className="px-2 py-1.5 font-medium whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line/30">
          {rows.map((cells, i) => (
            <tr key={i} className="text-ink hover:bg-surface-2/40">
              {cells.map((cell, j) => (
                <td key={j} className="px-2 py-1.5 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PipelineDetailPanel({ reviewId }: { reviewId: number }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["review-pipeline", reviewId],
    queryFn: () => api<ReviewPipelineDetail>(`/review/${reviewId}/pipeline`),
  });

  if (isLoading) {
    return <p className="text-xs text-ink-soft py-2">Loading pipeline details…</p>;
  }
  if (isError) {
    return (
      <p className="text-xs text-negative py-2">
        {(error as Error).message || "Could not load pipeline details"}
      </p>
    );
  }
  if (!data) return null;

  const diag = data.signal_diagnostics;
  const fired = diag?.fired ?? [];
  const notFired = diag?.not_fired ?? [];

  const extractedRows = data.extracted_values.map((ev: ReviewPipelineExtracted) => [
    <span key="l" className="font-medium">
      {ev.label}
    </span>,
    <span key="v" className="num">
      {formatPipelineValue(ev.value, ev.unit)}
    </span>,
    ev.page_number != null ? <span key="p" className="num text-ink-mute">p{ev.page_number}</span> : "—",
    ev.confidence_score != null ? (
      <span key="c" className="num text-ink-mute">
        {ev.confidence_score.toFixed(0)}%
      </span>
    ) : (
      "—"
    ),
    ev.statement_type ? (
      <span key="s" className="text-ink-soft">
        {ev.statement_type.replace(/_/g, " ")}
      </span>
    ) : (
      "—"
    ),
  ]);

  const factRows = data.facts.map((f: ReviewPipelineFact) => [
    <span key="c" className="font-medium">
      {f.normalized_code}
    </span>,
    <span key="n" className="text-ink-mute">
      {f.display_name}
    </span>,
    <span key="v" className="num">
      {formatPipelineValue(f.value, f.unit)}
    </span>,
    <span key="t" className="text-ink-soft">
      {f.period_value_type} · {f.consolidation}
    </span>,
  ]);

  const metricRows = data.metrics.map((m: ReviewPipelineMetric) => [
    <span key="c" className="font-medium">
      {m.metric_code}
    </span>,
    <span key="n" className="text-ink-mute">
      {m.metric_name}
    </span>,
    <span key="v" className="num">
      {m.metric_value != null ? formatPipelineValue(m.metric_value, m.unit) : "—"}
    </span>,
    m.change_percent != null ? (
      <span key="ch" className="num text-ink-mute">
        {m.change_percent > 0 ? "+" : ""}
        {m.change_percent.toFixed(1)}%
      </span>
    ) : (
      "—"
    ),
  ]);

  return (
    <div className="space-y-4 border-t border-line/40 pt-3 mt-1">
      {data.job ? (
        <div className="rounded-lg bg-surface-2/60 px-3 py-2 text-xs space-y-1">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-ink-mute">
            <span>
              Job <span className="num text-ink">#{data.job.job_id}</span> · {data.job.status}
            </span>
            {data.job.model_name ? <span>{data.job.model_name}</span> : null}
            {data.period ? <span>{data.period.display_label}</span> : null}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-ink-soft">
            {data.job.input_tokens != null ? (
              <span className="num">
                {data.job.input_tokens.toLocaleString()} in /{" "}
                {(data.job.output_tokens ?? 0).toLocaleString()} out tokens
              </span>
            ) : null}
            {data.job.started_at && data.job.completed_at ? (
              <span>
                {new Date(data.job.started_at).toLocaleTimeString()} –{" "}
                {new Date(data.job.completed_at).toLocaleTimeString()}
              </span>
            ) : null}
          </div>
          {Object.keys(data.job.stages).length > 0 ? (
            <PipelineStages stages={data.job.stages} />
          ) : null}
        </div>
      ) : null}

      <section className="space-y-1.5">
        <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">
          Extracted values ({data.extracted_values.length})
        </h3>
        <DataTable
          headers={["Label", "Value", "Page", "Conf.", "Statement"]}
          rows={extractedRows}
          empty="No extracted values for this document."
        />
      </section>

      <section className="space-y-1.5">
        <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">
          Financial facts ({data.facts.length})
        </h3>
        <DataTable
          headers={["Code", "Name", "Value", "Period"]}
          rows={factRows}
          empty="No normalized facts."
        />
      </section>

      <section className="space-y-1.5">
        <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">
          Calculated metrics ({data.metrics.length})
        </h3>
        <DataTable
          headers={["Code", "Name", "Value", "Change %"]}
          rows={metricRows}
          empty={
            data.period
              ? "No metrics calculated for this period."
              : "No financial period linked — metrics skipped."
          }
        />
      </section>

      <section className="space-y-1.5">
        <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">
          Generated signals ({data.signals.length})
        </h3>
        {data.signals.length === 0 ? (
          <p className="text-xs text-ink-soft">No signals generated.</p>
        ) : (
          <ul className="text-xs space-y-1">
            {data.signals.map((s) => (
              <li key={s.signal_id} className="flex flex-wrap gap-2 items-baseline">
                <span className="font-medium text-ink">{s.signal_name}</span>
                <span className="text-ink-soft">{s.signal_code}</span>
                <SeverityBadge level={s.severity} />
                <span className="text-ink-mute">
                  {s.is_published ? "published" : "unpublished"}
                </span>
                {s.headline ? <span className="text-ink-mute truncate">{s.headline}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-1.5">
        <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">
          Intelligence cards ({data.cards.length})
        </h3>
        {data.cards.length === 0 ? (
          <p className="text-xs text-ink-soft">No cards generated.</p>
        ) : (
          <ul className="text-xs space-y-1.5">
            {data.cards.map((c) => (
              <li key={c.card_id} className="rounded-md border border-line/30 px-2 py-1.5">
                <div className="font-medium text-ink">{c.headline}</div>
                <div className="text-ink-mute">{c.one_line_summary}</div>
                <div className="text-ink-soft mt-0.5">
                  {c.card_type.replace(/_/g, " ")} · priority {c.card_priority.toFixed(0)} ·{" "}
                  {c.is_published ? "published" : "unpublished"}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {diag ? (
        <section className="space-y-2">
          <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">Signal rule evaluation</h3>
          <p className="text-xs text-ink-mute">
            <span className="num font-semibold text-ink">{diag.fired_count}</span> of{" "}
            {diag.rules_evaluable} metric rules fired
            {diag.rules_non_evaluable > 0
              ? ` · ${diag.rules_non_evaluable} need text/fact extraction`
              : ""}
          </p>
          {fired.length > 0 ? (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-positive mb-1">Fired</p>
              <ul className="text-xs text-ink-mute space-y-0.5">
                {fired.map((s) => (
                  <li key={s.signal_code}>
                    <span className="text-positive font-medium">✓</span> {s.signal_name}
                    {s.headline ? ` — ${s.headline}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {notFired.length > 0 ? (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-ink-soft mb-1">
                Did not fire ({notFired.length})
              </p>
              <ul className="text-xs space-y-1.5 max-h-64 overflow-y-auto pr-1">
                {notFired.map((skip) => (
                  <li key={skip.signal_code} className="border-b border-line/20 pb-1 last:border-0">
                    <div className="font-medium text-ink">{skip.signal_name}</div>
                    <div className="text-ink-soft">{skipReasonLabel(skip)}</div>
                    <div className="text-ink-mute">{skip.detail}</div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function canApproveReview(item: ReviewItem): boolean {
  return item.status === "OPEN";
}

/** Allow reject on open items and on already-published (auto or manual) jobs. */
function canRejectReview(item: ReviewItem): boolean {
  if (item.status === "REJECTED") return false;
  if (item.status === "OPEN") return true;
  if (item.auto_published) return true;
  return item.status === "APPROVED" || item.status === "RESOLVED";
}

function ReviewCard({
  item,
  pipelineExpanded,
  onTogglePipeline,
  onApprove,
  onReject,
  busy,
}: {
  item: ReviewItem;
  pipelineExpanded: boolean;
  onTogglePipeline: () => void;
  onApprove: () => void;
  onReject: (opts?: { confirmPublished?: boolean }) => void;
  busy: boolean;
}) {
  const diag = item.signal_diagnostics;
  const fired = diag?.fired ?? [];
  const evaluable = diag?.rules_evaluable ?? 0;
  const firedCount = diag?.fired_count ?? 0;

  return (
    <article className="card p-4 md:p-5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold text-ink truncate">
              {item.company_name ?? "Unknown company"}
              {item.company_symbol ? (
                <span className="text-ink-soft font-normal text-sm"> · {item.company_symbol}</span>
              ) : null}
            </h2>
            <SeverityBadge level={item.priority} />
            <span className="text-[11px] uppercase tracking-wider text-ink-soft px-1.5 py-0.5 rounded bg-surface-2">
              {item.status}
            </span>
            {item.auto_published ? (
              <span className="text-[11px] text-positive font-medium">Auto-published</span>
            ) : null}
          </div>
          <p className="text-sm text-ink-mute">
            {item.document_title ?? "No document"}
            {item.document_type ? (
              <span className="text-ink-soft"> · {item.document_type.replace(/_/g, " ")}</span>
            ) : null}
          </p>
          {item.issue_description ? (
            <p className="text-sm text-ink leading-snug">{item.issue_description}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <div className="text-right text-xs text-ink-soft">
            <div className="num text-sm font-medium text-ink">
              {item.extraction_confidence != null
                ? `${item.extraction_confidence.toFixed(0)}%`
                : "—"}
            </div>
            <div>confidence</div>
            <div className="text-[10px] mt-0.5">
              auto-publish ≥ {item.auto_publish_threshold.toFixed(0)}%
            </div>
          </div>
          <div className="flex gap-1">
            {canApproveReview(item) ? (
              <button className="btn-primary text-xs" disabled={busy} onClick={onApprove}>
                Approve
              </button>
            ) : null}
            {canRejectReview(item) ? (
              <button
                className={clsx(
                  "text-xs",
                  item.auto_published || item.status === "RESOLVED" || item.status === "APPROVED"
                    ? "btn-ghost border border-negative/40 text-negative"
                    : "btn-ghost",
                )}
                disabled={busy}
                onClick={() => onReject({ confirmPublished: !canApproveReview(item) })}
              >
                {item.auto_published || item.status === "RESOLVED" || item.status === "APPROVED"
                  ? "Reject & unpublish"
                  : "Reject"}
              </button>
            ) : item.status === "REJECTED" ? (
              <span className="text-[11px] text-ink-soft px-2 py-1">Unpublished</span>
            ) : null}
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1.5">
          <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">Pipeline output</h3>
          <PipelineStages stages={item.pipeline_stages ?? {}} />
        </div>
        <div className="space-y-1.5">
          <h3 className="text-[11px] uppercase tracking-wider text-ink-soft">Signals</h3>
          {diag ? (
            <p className="text-sm text-ink">
              <span className="num font-semibold">{firedCount}</span>
              <span className="text-ink-mute">
                {" "}
                of {evaluable} metric rules fired
                {diag.rules_non_evaluable > 0
                  ? ` · ${diag.rules_non_evaluable} need text/fact extraction`
                  : ""}
              </span>
            </p>
          ) : (
            <p className="text-sm text-ink-soft">No signal evaluation yet</p>
          )}
          {fired.length > 0 ? (
            <ul className="text-xs text-ink-mute space-y-0.5">
              {fired.slice(0, 3).map((s) => (
                <li key={s.signal_code} className="truncate">
                  <span className="text-positive font-medium">✓</span> {s.signal_name}
                </li>
              ))}
              {fired.length > 3 ? (
                <li className="text-ink-soft">+{fired.length - 3} more</li>
              ) : null}
            </ul>
          ) : diag?.blockers?.length ? (
            <p className="text-xs text-ink-soft">
              {diag.blockers.includes("no_period")
                ? "Skipped — document has no financial period linked."
                : diag.blockers.includes("no_metrics")
                  ? "Skipped — no calculated metrics for this period."
                  : "Signal evaluation blocked."}
            </p>
          ) : diag ? (
            <p className="text-xs text-ink-soft">No metric rules breached for this filing.</p>
          ) : null}
        </div>
      </div>

      {item.publish_blocked_reasons.length > 0 && !item.auto_published ? (
        <div className="rounded-lg border border-mixed/30 bg-mixed-bg/40 px-3 py-2">
          <h3 className="text-[11px] uppercase tracking-wider text-mixed font-medium mb-1">
            Why not auto-published
          </h3>
          <ul className="text-sm text-ink-mute list-disc list-inside space-y-0.5">
            {item.publish_blocked_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {item.job_error ? (
        <p className="text-sm text-negative">Job error: {item.job_error}</p>
      ) : null}

      <div>
        <button
          type="button"
          className="text-xs font-medium text-ink-soft hover:text-ink underline-offset-2 hover:underline"
          onClick={onTogglePipeline}
        >
          {pipelineExpanded ? "Hide" : "Show"} pipeline details
          {item.document_id
            ? ` (extracted, facts, metrics, signals, cards)`
            : ""}
        </button>
        {pipelineExpanded ? <PipelineDetailPanel reviewId={item.review_id} /> : null}
      </div>
    </article>
  );
}

export function AdminReviewPage() {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"open" | "all">("open");
  const [expandedPipelineId, setExpandedPipelineId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["review", filter],
    queryFn: () =>
      api<ReviewItem[]>(filter === "open" ? "/review?status_filter=OPEN" : "/review"),
    enabled: user?.user_type === "ADMIN",
  });

  const updateStatus = useMutation({
    mutationFn: async ({
      id,
      status,
    }: {
      id: number;
      status: string;
      reviewId?: number;
    }) => {
      return api(`/review/${id}`, { method: "PATCH", body: { status } });
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["review"] });
      if (vars.status === "REJECTED" || vars.status === "APPROVED") {
        qc.invalidateQueries({ queryKey: ["feedSummary"] });
        qc.invalidateQueries({ queryKey: ["feed"] });
        qc.invalidateQueries({ queryKey: ["extraction-jobs"] });
      }
      if (vars.reviewId != null) {
        qc.invalidateQueries({ queryKey: ["review-pipeline", vars.reviewId] });
      }
    },
  });

  const handleReject = (reviewId: number, confirmPublished?: boolean) => {
    if (confirmPublished) {
      const ok = window.confirm(
        "Reject and remove from the feed?\n\nThis unpublishes every card, signal, and event tied to this document. Extraction data stays in the database so you can re-approve later.",
      );
      if (!ok) return;
    }
    updateStatus.mutate({ id: reviewId, status: "REJECTED", reviewId });
  };

  if (user && user.user_type !== "ADMIN") return <Navigate to="/" replace />;

  const openCount = data?.length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Review Queue</h1>
          <p className="text-sm text-ink-mute">
            Ingestion results awaiting approval — signal counts, pipeline stages, and full
            extraction drill-down per job. Use <strong className="font-medium text-ink">All</strong>{" "}
            to reject jobs that already auto-published and remove them from the feed.
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-line/60 p-0.5 text-xs">
          <button
            type="button"
            className={`px-3 py-1.5 rounded-md ${filter === "open" ? "bg-surface-2 font-medium text-ink" : "text-ink-soft"}`}
            onClick={() => setFilter("open")}
          >
            Open
          </button>
          <button
            type="button"
            className={`px-3 py-1.5 rounded-md ${filter === "all" ? "bg-surface-2 font-medium text-ink" : "text-ink-soft"}`}
            onClick={() => setFilter("all")}
          >
            All
          </button>
        </div>
      </div>

      {isLoading ? (
        <PageLoader />
      ) : !data || data.length === 0 ? (
        <div className="card p-6 text-sm text-ink-mute text-center">
          {filter === "open" ? "No open items — queue is clear." : "No review items."}
        </div>
      ) : (
        <div className="space-y-3">
          {filter === "open" ? (
            <p className="text-xs text-ink-soft">{openCount} open item(s)</p>
          ) : null}
          {data.map((r) => (
            <ReviewCard
              key={r.review_id}
              item={r}
              pipelineExpanded={expandedPipelineId === r.review_id}
              onTogglePipeline={() =>
                setExpandedPipelineId((id) => (id === r.review_id ? null : r.review_id))
              }
              onApprove={() =>
                updateStatus.mutate({ id: r.review_id, status: "APPROVED", reviewId: r.review_id })
              }
              onReject={(opts) => handleReject(r.review_id, opts?.confirmPublished)}
              busy={updateStatus.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}
