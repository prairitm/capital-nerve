import { useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import type { MetricValue } from "@/api/types";

type MetricCalculationData = MetricValue["calculation_data"];

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function metricFormula(calculationData?: MetricCalculationData | null): string | null {
  if (!calculationData || typeof calculationData !== "object") return null;
  return stringValue(calculationData.formula);
}

export function MetricFormulaInfo({
  calculationData,
  metricName,
}: {
  calculationData?: MetricCalculationData | null;
  metricName: string;
}) {
  const [open, setOpen] = useState(false);
  const formula = metricFormula(calculationData);

  const panel = open
    ? createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-bg/60 px-4"
          role="presentation"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-lg border border-line bg-surface-2 p-4 text-left shadow-card"
            role="dialog"
            aria-modal="true"
            aria-label={`Formula for ${metricName}`}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-soft">
              Formula
            </div>
            <div className="mt-2 break-words font-mono text-xs leading-relaxed text-ink">
              {formula ?? "Formula unavailable for this metric."}
            </div>
            <button
              type="button"
              className="btn-secondary mt-4 px-2.5 py-1.5 text-xs"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <span className="relative inline-flex shrink-0">
      <button
        type="button"
        className="inline-flex size-5 items-center justify-center rounded-full border border-line text-ink-soft transition-colors hover:border-line-strong hover:text-ink focus:outline-none focus:ring-2 focus:ring-line-strong"
        aria-label={`Show formula for ${metricName}`}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <Info size={12} aria-hidden="true" />
      </button>
      {panel}
    </span>
  );
}
