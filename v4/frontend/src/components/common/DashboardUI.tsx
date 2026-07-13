import type { ReactNode } from "react";
import { AlertCircle, ArrowDownRight, ArrowUpRight, RefreshCw } from "lucide-react";
import clsx from "clsx";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h1 className="text-2xl md:text-[28px] leading-tight font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-ink-mute">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

export function StatusSummary({ items }: { items: Array<{ label: string; value: ReactNode; hint?: string; tone?: "default" | "positive" | "negative" | "warning" }> }) {
  return (
    <section className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line lg:grid-cols-4" aria-label="Intelligence summary">
      {items.map((item) => (
        <div key={item.label} className="bg-surface px-4 py-4 md:px-5">
          <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-soft">{item.label}</div>
          <div className={clsx("mt-2 text-2xl font-semibold tracking-tight num", item.tone === "positive" && "text-positive", item.tone === "negative" && "text-negative", item.tone === "warning" && "text-mixed", (!item.tone || item.tone === "default") && "text-ink")}>{item.value}</div>
          {item.hint && <div className="mt-1 text-xs text-ink-mute">{item.hint}</div>}
        </div>
      ))}
    </section>
  );
}

export function MetricCard({ label, value, prior, change }: { label: string; value: string; prior?: string; change?: number | null }) {
  const positive = change != null && change > 0;
  const negative = change != null && change < 0;
  return (
    <div className="rounded-xl border border-line/70 bg-surface-2/45 p-4">
      <div className="text-xs font-medium text-ink-mute">{label}</div>
      <div className="mt-2 text-xl font-semibold tracking-tight text-ink num">{value}</div>
      <div className="mt-2 flex min-h-5 items-center justify-between gap-2 text-xs">
        <span className="text-ink-soft num">{prior ? `Prior ${prior}` : "Latest reported"}</span>
        {change != null && (
          <span className={clsx("inline-flex items-center gap-1 font-semibold num", positive ? "text-positive" : negative ? "text-negative" : "text-ink-mute")}>
            {positive ? <ArrowUpRight size={13} /> : negative ? <ArrowDownRight size={13} /> : null}
            {positive ? "+" : ""}{change.toFixed(1)}% YoY
          </span>
        )}
      </div>
    </div>
  );
}

export function PageSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="mx-auto max-w-6xl space-y-5" aria-label="Loading" role="status">
      <div className="skeleton h-7 w-56" />
      <div className="skeleton h-4 w-80 max-w-full" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-24" />)}
      </div>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton h-28" />)}
    </div>
  );
}

export function ErrorState({ title = "Unable to load data", description = "Check the connection and try again.", onRetry }: { title?: string; description?: string; onRetry?: () => void }) {
  return (
    <div className="card flex flex-col items-center px-6 py-12 text-center" role="alert">
      <div className="grid size-10 place-items-center rounded-full bg-negative-bg text-negative"><AlertCircle size={19} /></div>
      <h2 className="mt-4 text-base font-semibold text-ink">{title}</h2>
      <p className="mt-1 max-w-md text-sm text-ink-mute">{description}</p>
      {onRetry && <button type="button" onClick={onRetry} className="btn-secondary mt-5"><RefreshCw size={15} />Retry</button>}
    </div>
  );
}
