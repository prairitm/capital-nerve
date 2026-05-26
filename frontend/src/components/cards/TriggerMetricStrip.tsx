import { useState } from "react";
import clsx from "clsx";
import type { IOTriggerMetricBrief } from "@/api/types";
import { MetricConfidenceBadge } from "@/components/common/MetricConfidenceBadge";
import { MetricKindBadge } from "@/components/common/MetricKindBadge";
import { MetricRegistryDrawer } from "@/components/common/MetricRegistryDrawer";
import { MetricValidationBadge } from "@/components/common/MetricValidationBadge";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";

interface Props {
  metric: IOTriggerMetricBrief | null | undefined;
  documentId: number | null | undefined;
  className?: string;
}

const COMPARISON_LABEL: Record<string, string> = {
  qoq: "QoQ",
  yoy: "YoY",
  yoy_and_qoq: "YoY & QoQ",
  pp_vs_prior_yoy: "Δ vs prior YoY (pp)",
};

/**
 * Two-line strip rendered between the card headline and the source row.
 *
 * Line 1: metric kind + name + value + comparator label + validation status.
 * Line 2: formula + clickable source-page link.
 *
 * This is the analyst-trust upgrade — every feed row now answers
 * "what kind of number is this, how was it computed, and where did it come
 * from" without the user opening the card.
 */
export function TriggerMetricStrip({ metric, documentId, className }: Props) {
  const [registryOpen, setRegistryOpen] = useState(false);
  if (!metric) return null;
  const {
    code,
    name,
    value_display,
    metric_kind,
    comparison_type,
    formula_text,
    source_page,
    validation_status,
    validation_reason,
    confidence_band,
    confidence_score,
  } = metric;

  const comparator = comparison_type ? COMPARISON_LABEL[comparison_type] ?? null : null;
  const showSecondLine = Boolean(formula_text || (documentId && source_page));

  if (!name && !value_display && !showSecondLine) return null;

  return (
    <>
      <div
        className={clsx("space-y-1 rounded-lg border border-line/40 bg-surface-2/30 px-2.5 py-1.5", className)}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <MetricKindBadge kind={metric_kind ?? null} />
          {name && code ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setRegistryOpen(true);
              }}
              className="text-xs font-medium text-ink underline-offset-2 hover:underline"
              title="Open metric definition"
            >
              {name}
            </button>
          ) : name ? (
            <span className="text-xs font-medium text-ink">{name}</span>
          ) : null}
          {value_display && (
            <span className="text-xs font-semibold text-ink tabular-nums">{value_display}</span>
          )}
          {comparator && (
            <span className="text-[10px] uppercase tracking-wider text-ink-soft">{comparator}</span>
          )}
          <MetricValidationBadge status={validation_status} reason={validation_reason} />
          {confidence_band && (
            <MetricConfidenceBadge band={confidence_band} score={confidence_score} />
          )}
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
