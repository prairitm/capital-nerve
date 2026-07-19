import { useEffect, useState } from "react";
import { CheckCircle2, ClipboardCheck, FileSearch, RotateCcw, Search, XCircle } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import clsx from "clsx";
import { api } from "@/api/client";
import type {
  FactReviewCandidate,
  FactReviewItem,
  FactReviewResponse,
  FactReviewSummary,
  ReviewQueueStatus,
} from "@/api/types";
import { ErrorState, PageHeader, PageSkeleton, StatusSummary } from "@/components/common/DashboardUI";
import { Empty } from "@/components/common/Empty";
import { Spinner } from "@/components/common/Spinner";
import { documentSourceHref } from "@/lib/documentSource";
import { basisLabel, formatDate, formatMetricValue } from "@/lib/format";

type QueueFilter = ReviewQueueStatus | "all";

const FILTERS: Array<{ value: QueueFilter; label: string }> = [
  { value: "open", label: "Open" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

export function AdminReviews() {
  const [filter, setFilter] = useState<QueueFilter>("open");
  const [search, setSearch] = useState("");
  const summary = useQuery({
    queryKey: ["admin-review-summary"],
    queryFn: () => api<FactReviewSummary>("/admin/reviews/summary"),
  });
  const reviews = useQuery({
    queryKey: ["admin-reviews", filter, search],
    queryFn: () => api<FactReviewResponse>("/admin/reviews", { query: { queue_status: filter, search, limit: 200 } }),
  });

  if (reviews.isLoading || summary.isLoading) return <PageSkeleton rows={5} />;
  if (reviews.isError || summary.isError) {
    const error = reviews.error || summary.error;
    return <ErrorState title="Unable to load review queue" description={(error as Error).message} onRetry={() => { void reviews.refetch(); void summary.refetch(); }} />;
  }

  const counts = summary.data ?? { open: 0, approved: 0, rejected: 0, total: 0 };
  const items = reviews.data?.items ?? [];
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        eyebrow="Administration"
        title="Fact review queue"
        description="Inspect uncertain observations and record an audited decision. Approval here does not auto-publish or modify the analytics database."
        action={<span className="chip-mixed"><ClipboardCheck size={12} />{counts.open} open</span>}
      />
      <StatusSummary items={[
        { label: "Open", value: counts.open, hint: "Needs a decision", tone: counts.open ? "warning" : "default" },
        { label: "Approved", value: counts.approved, hint: "Observation selected", tone: "positive" },
        { label: "Rejected", value: counts.rejected, hint: "Held from publication", tone: counts.rejected ? "negative" : "default" },
        { label: "Total", value: counts.total, hint: "Current review-required facts" },
      ]} />
      <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="inline-flex w-fit rounded-xl border border-line bg-surface p-1">
          {FILTERS.map((item) => (
            <button key={item.value} type="button" onClick={() => setFilter(item.value)} className={clsx("focus-ring rounded-lg px-3 py-1.5 text-xs font-medium transition-colors", filter === item.value ? "bg-surface-3 text-ink" : "text-ink-mute hover:text-ink")}>
              {item.label}
            </button>
          ))}
        </div>
        <label className="relative block w-full sm:max-w-sm">
          <span className="sr-only">Search review queue</span>
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
          <input className="input pl-9" placeholder="Search company, fact, or evidence" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
      </section>
      {items.length ? (
        <section className="space-y-4">
          {items.map((item) => <ReviewCard key={item.resolved_fact_id} item={item} />)}
        </section>
      ) : (
        <Empty
          icon={<ClipboardCheck size={24} />}
          title={filter === "open" ? "No facts need review" : `No ${filter} reviews`}
          description={search ? "Try a broader search." : "The queue will populate when extraction routes a fact to review or abstains for missing evidence."}
        />
      )}
    </div>
  );
}

function ReviewCard({ item }: { item: FactReviewItem }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(item.decision?.selected_observation_id ?? item.selected_observation_id ?? item.candidates[0]?.observation_id ?? "");
  const [note, setNote] = useState(item.decision?.reviewer_note ?? "");
  useEffect(() => {
    setSelected(item.decision?.selected_observation_id ?? item.selected_observation_id ?? item.candidates[0]?.observation_id ?? "");
    setNote(item.decision?.reviewer_note ?? "");
  }, [item]);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["admin-reviews"] });
    void queryClient.invalidateQueries({ queryKey: ["admin-review-summary"] });
  };
  const decide = useMutation({
    mutationFn: (decision: "approved" | "rejected") => api<FactReviewItem>(`/admin/reviews/${item.resolved_fact_id}/decision`, {
      method: "POST",
      body: { decision, selected_observation_id: decision === "approved" ? selected : null, reviewer_note: note || null },
    }),
    onSuccess: refresh,
  });
  const reopen = useMutation({
    mutationFn: () => api<{ reopened: boolean }>(`/admin/reviews/${item.resolved_fact_id}/decision`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const mutationError = decide.error || reopen.error;
  return (
    <article className="card overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line/60 px-4 py-4 md:px-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-ink">{item.company_symbol || item.company_name || "Company"}</span>
            <StatusChip status={item.queue_status} />
            {item.basis && <span className="chip-neutral">{basisLabel(item.basis)}</span>}
            {item.period_type && <span className="chip-neutral">{basisLabel(item.period_type)}</span>}
          </div>
          <h2 className="mt-2 text-base font-semibold text-ink">{item.fact_name || basisLabel(item.fact_code)}</h2>
          <p className="mt-1 text-xs text-ink-mute">{formatDate(item.event_date)}{item.period ? ` · period ended ${formatDate(item.period)}` : ""}</p>
        </div>
        <div className="text-right">
          <div className="num text-lg font-semibold text-ink">{item.resolved_value != null ? formatMetricValue(item.resolved_value, item.unit) : item.resolved_value_text || "—"}</div>
          <div className="mt-1 text-[11px] text-ink-soft">Candidate selected by extraction</div>
        </div>
      </div>
      <div className="space-y-4 p-4 md:p-5">
        <div className="space-y-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-soft">Observations</div>
          {item.candidates.map((candidate) => (
            <CandidateRow key={candidate.observation_id} groupName={item.resolved_fact_id} candidate={candidate} selected={selected === candidate.observation_id} disabled={item.queue_status !== "open"} onSelect={() => setSelected(candidate.observation_id)} />
          ))}
        </div>
        {item.queue_status === "open" ? (
          <div className="space-y-3 border-t border-line/60 pt-4">
            <label><span className="mb-1 block text-[11px] text-ink-soft">Reviewer note <span className="text-ink-soft">(required for rejection)</span></span><textarea className="input min-h-20 resize-y" maxLength={2000} placeholder="Record what you checked or why the fact should remain withheld." value={note} onChange={(event) => setNote(event.target.value)} /></label>
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" className="btn-secondary text-negative" disabled={decide.isPending || !note.trim()} onClick={() => decide.mutate("rejected")}><XCircle size={15} />Reject</button>
              <button type="button" className="btn-primary" disabled={decide.isPending || !selected} onClick={() => decide.mutate("approved")}>{decide.isPending ? <Spinner /> : <CheckCircle2 size={15} />}Approve selected</button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line/60 pt-4">
            <div className="text-xs text-ink-mute"><span className="font-medium text-ink">{item.decision?.reviewer_name || item.decision?.reviewer_email || "Administrator"}</span> · {formatDate(item.decision?.reviewed_at)}{item.decision?.decision === "approved" && item.decision.application_status === "pending" ? <span className="block mt-1 text-warning">Awaiting controlled reconciliation</span> : null}{item.decision?.application_status === "failed" ? <span className="block mt-1 text-negative">Reconciliation blocked: {item.decision.application_error || "validation failed"}</span> : null}{item.decision?.reviewer_note ? <span className="block mt-1 text-ink-soft">{item.decision.reviewer_note}</span> : null}</div>
            <button type="button" className="btn-secondary" disabled={reopen.isPending || item.decision?.application_status === "applied"} onClick={() => reopen.mutate()}>{reopen.isPending ? <Spinner /> : <RotateCcw size={14} />}Reopen</button>
          </div>
        )}
        {mutationError && <p className="text-sm text-negative" role="alert">{(mutationError as Error).message}</p>}
      </div>
    </article>
  );
}

function CandidateRow({ groupName, candidate, selected, disabled, onSelect }: { groupName: string; candidate: FactReviewCandidate; selected: boolean; disabled: boolean; onSelect: () => void }) {
  const value = candidate.value != null ? formatMetricValue(candidate.value, candidate.unit) : candidate.value_text || "—";
  return (
    <label className={clsx("flex gap-3 rounded-xl border p-3 transition-colors", selected ? "border-brand/60 bg-brand/5" : "border-line/70 bg-surface-2/40", disabled ? "cursor-default" : "cursor-pointer hover:border-line-strong")}>
      <input type="radio" name={`observation-${groupName}`} checked={selected} disabled={disabled} onChange={onSelect} className="mt-1 accent-blue-500" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2"><span className="num text-sm font-semibold text-ink">{value}</span><span className="text-[11px] text-ink-soft">{candidate.extraction_method || "unknown method"}{candidate.confidence != null ? ` · ${(candidate.confidence * 100).toFixed(0)}% confidence` : ""}</span></div>
        <p className="mt-1 break-words text-xs leading-5 text-ink-mute">{candidate.source_text || "No source text supplied."}</p>
        <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-ink-soft"><span>{candidate.source_page ? `PDF page ${candidate.source_page}` : "No source page"}</span>{candidate.document_id && <Link className="ui-link inline-flex items-center gap-1" to={documentSourceHref(candidate.document_id, { page: candidate.source_page, highlight: candidate.source_text, value: candidate.value ?? candidate.value_text, context: candidate.basis })}><FileSearch size={13} />Open evidence</Link>}</div>
      </div>
    </label>
  );
}

function StatusChip({ status }: { status: ReviewQueueStatus }) {
  if (status === "approved") return <span className="chip-positive">Approved</span>;
  if (status === "rejected") return <span className="chip-negative">Rejected</span>;
  return <span className="chip-mixed">Open</span>;
}
