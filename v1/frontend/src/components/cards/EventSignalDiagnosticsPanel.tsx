import { useState } from "react";
import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import type { EventSignalDiagnostics } from "@/api/types";

interface Props {
  diagnostics: EventSignalDiagnostics;
  className?: string;
}

function RuleTable({
  title,
  rows,
  tone,
}: {
  title: string;
  rows: EventSignalDiagnostics["fired"];
  tone: "positive" | "muted" | "neutral";
}) {
  if (rows.length === 0) return null;
  const toneClass =
    tone === "positive"
      ? "text-positive"
      : tone === "muted"
        ? "text-ink-mute"
        : "text-ink-soft";
  return (
    <div>
      <h3 className={clsx("text-xs uppercase tracking-wider font-semibold mb-2", toneClass)}>
        {title} ({rows.length})
      </h3>
      <ul className="space-y-1.5">
        {rows.map((row) => (
          <li
            key={row.signal_code}
            className="rounded-lg border border-line/40 bg-surface-2/30 px-3 py-2 text-sm"
          >
            <div className="font-medium text-ink">{row.signal_name}</div>
            {row.headline && (
              <div className="text-xs text-ink-mute mt-0.5">{row.headline}</div>
            )}
            {(row.reason || row.detail) && (
              <div className="text-[11px] text-ink-soft mt-1">
                {row.detail || row.reason}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Shows every signal rule evaluated for this event — fired, skipped, and
 * non-evaluable (concall / fact-only rules). Data comes from the pipeline
 * diagnostics stored on the extraction job.
 */
export function EventSignalDiagnosticsPanel({ diagnostics, className }: Props) {
  const [open, setOpen] = useState(false);
  const total = diagnostics.rules_total;
  if (total === 0) return null;

  return (
    <section className={clsx("card overflow-hidden", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-surface-2/40 transition-colors"
      >
        <div>
          <h2 className="text-base font-semibold">Signal rule evaluation</h2>
          <p className="text-xs text-ink-soft mt-0.5">
            {diagnostics.fired_count} fired · {diagnostics.not_fired.length} not fired ·{" "}
            {diagnostics.not_evaluable.length} need non-metric extractors
            {diagnostics.blockers.length > 0 &&
              ` · blocked: ${diagnostics.blockers.join(", ")}`}
          </p>
        </div>
        <ChevronDown
          size={18}
          className={clsx(
            "text-ink-soft shrink-0 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="px-5 pb-5 pt-0 space-y-4 border-t border-line/60">
          <RuleTable title="Fired" rows={diagnostics.fired} tone="positive" />
          <RuleTable title="Not fired" rows={diagnostics.not_fired} tone="muted" />
          <RuleTable title="Not evaluable (metric rules)" rows={diagnostics.not_evaluable} tone="neutral" />
        </div>
      )}
    </section>
  );
}
