import { useState } from "react";
import clsx from "clsx";
import type { IOTriggerMetricBrief } from "@/api/types";
import { MetricKindBadge } from "@/components/common/MetricKindBadge";
import { MetricRegistryDrawer } from "@/components/common/MetricRegistryDrawer";
import { MetricValidationBadge } from "@/components/common/MetricValidationBadge";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import { formatDisplayValue } from "@/lib/format";

interface Props {
  metric: IOTriggerMetricBrief | null | undefined;
  documentId: number | null | undefined;
  className?: string;
  /** `highlight` — scannable card row with prominent value, no formula. */
  variant?: "default" | "highlight";
}

const COMPARISON_LABEL: Record<string, string> = {
  qoq: "QoQ",
  yoy: "YoY",
  yoy_and_qoq: "YoY & QoQ",
  pp_vs_prior_yoy: "Δ vs prior YoY (pp)",
};

function MetricName({
  name,
  code,
  onOpenRegistry,
}: {
  name: string;
  code: string | null | undefined;
  onOpenRegistry: () => void;
}) {
  if (code) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onOpenRegistry();
        }}
        className="text-xs font-medium text-ink truncate underline-offset-2 hover:underline"
        title="Open metric definition"
      >
        {name}
      </button>
    );
  }
  return <span className="text-xs font-medium text-ink truncate">{name}</span>;
}

/**
 * Two-line strip rendered between the card headline and the source row.
 *
 * Line 1: metric kind + name + value + comparator label + validation status.
 * Line 2: formula + clickable source-page link.
 *
 * `highlight` variant collapses to a single scannable row for feed cards.
 */
export function TriggerMetricStrip({
  metric,
  documentId,
  className,
  variant = "default",
}: Props) {
  const [registryOpen, setRegistryOpen] = useState(false);
  if (!metric) return null;
  const {
    code,
    name,
    value_display,
    unit,
    metric_kind,
    comparison_type,
    formula_text,
    source_page,
    validation_status,
    validation_reason,
  } = metric;

  const comparator = comparison_type ? (COMPARISON_LABEL[comparison_type] ?? null) : null;
  const showSecondLine = Boolean(formula_text || (documentId && source_page));

  if (!name && !value_display && !showSecondLine) return null;

  if (variant === "highlight") {
    return (
      <>
        <div
          className={clsx(
            "flex items-center justify-between gap-3 rounded-lg border border-line/50 bg-surface/40 px-3 py-2.5",
            className,
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-2 min-w-0">
            <MetricKindBadge kind={metric_kind ?? null} />
            {name ? (
              <MetricName
                name={name}
                code={code}
                onOpenRegistry={() => setRegistryOpen(true)}
              />
            ) : null}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {value_display && (
              <span className="num text-lg font-semibold text-ink tabular-nums leading-none">
                {formatDisplayValue(value_display, unit)}
              </span>
            )}
            {comparator && (
              <span className="text-[10px] uppercase tracking-wider text-ink-soft">{comparator}</span>
            )}
            <MetricValidationBadge status={validation_status} reason={validation_reason} />
          </div>
        </div>
        <MetricRegistryDrawer
          open={registryOpen}
          initialMetricCode={code}
          onClose={() => setRegistryOpen(false)}
        />
      </>
    );
  }

  return (
    <>
      <div
        className={clsx("space-y-1 rounded-lg border border-line/40 bg-surface-2/30 px-2.5 py-1.5", className)}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <MetricKindBadge kind={metric_kind ?? null} />
          {name ? (
            <MetricName
              name={name}
              code={code}
              onOpenRegistry={() => setRegistryOpen(true)}
            />
          ) : null}
          {value_display && (
            <span className="text-xs font-semibold text-ink tabular-nums">
              {formatDisplayValue(value_display, unit)}
            </span>
          )}
          {comparator && (
            <span className="text-[10px] uppercase tracking-wider text-ink-soft">{comparator}</span>
          )}
          <MetricValidationBadge status={validation_status} reason={validation_reason} />
        </div>
        {showSecondLine && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink-soft">
            {formula_text && (
              <code className="font-mono text-[11px] text-ink-mute" title="Formula">
                {formula_text}
              </code>
            )}
            {documentId && source_page != null && (
              <>
                {formula_text && <span className="text-line">·</span>}
                <SourceDocumentLink
                  documentId={documentId}
                  page={source_page}
                  label={`p.${source_page}`}
                  onClick={(e) => e.stopPropagation()}
                />
              </>
            )}
          </div>
        )}
      </div>
      <MetricRegistryDrawer
        open={registryOpen}
        initialMetricCode={code}
        onClose={() => setRegistryOpen(false)}
      />
    </>
  );
}
