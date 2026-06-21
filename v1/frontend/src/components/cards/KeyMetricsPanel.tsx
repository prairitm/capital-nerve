import clsx from "clsx";
import type { EvidenceItem, IOMetric } from "@/api/types";
import { CALCULATION_CHAIN_ANCHOR } from "@/components/evidence/CalculationChainPanel";
import {
  EvidenceInlineLinks,
  evidenceMatchingLabel,
} from "@/components/evidence/EvidenceInlineLink";
import { formatIOMetricValue } from "@/lib/format";

interface Props {
  metrics: IOMetric[];
  evidence: EvidenceItem[];
  calculationChain?: unknown | null;
  subtitle?: string | null;
  variant?: "page" | "drawer";
  className?: string;
}

type MetricSourceKind = "extracted" | "computed";

function metricSourceKind(metric: IOMetric, evidence: EvidenceItem[]): MetricSourceKind {
  if (metric.source_kind === "extracted" || metric.source_kind === "computed") {
    return metric.source_kind;
  }
  const hasSource = evidenceMatchingLabel(evidence, metric.name).some((e) => e.document_id != null);
  return hasSource ? "extracted" : "computed";
}

function partitionMetrics(
  metrics: IOMetric[],
  evidence: EvidenceItem[],
): { extracted: IOMetric[]; computed: IOMetric[] } {
  const extracted: IOMetric[] = [];
  const computed: IOMetric[] = [];
  for (const metric of metrics) {
    if (metricSourceKind(metric, evidence) === "extracted") {
      extracted.push(metric);
    } else {
      computed.push(metric);
    }
  }
  return { extracted, computed };
}

function MetricRows({
  rows,
  evidence,
  showSource,
  linkDerivation,
  isPage,
}: {
  rows: IOMetric[];
  evidence: EvidenceItem[];
  showSource: boolean;
  linkDerivation: boolean;
  isPage: boolean;
}) {
  const derivationProps = linkDerivation
    ? {
        href: `#${CALCULATION_CHAIN_ANCHOR}`,
        title: "Open derivation",
      }
    : {};

  return (
    <>
      {isPage && (
        <div
          className={clsx(
            "hidden sm:grid gap-4 px-0 py-2 text-[11px] uppercase tracking-wider text-ink-soft border-b border-line/40",
            showSource ? "sm:grid-cols-[1fr_auto_4.5rem]" : "sm:grid-cols-[1fr_auto]",
          )}
        >
          <span>Metric</span>
          <span className="text-right">Value</span>
          {showSource && <span className="text-right">Source</span>}
        </div>
      )}

      <div
        className={clsx(
          !isPage && "rounded-xl border border-line/60 overflow-hidden divide-y divide-line/40",
        )}
      >
        {rows.map((m, i) => {
          const rowEvidence = evidenceMatchingLabel(evidence, m.name);
          const formatted = formatIOMetricValue(m.value, m.unit);
          const Tag = linkDerivation ? "a" : "div";

          return (
            <Tag
              key={`${m.name}-${i}`}
              {...derivationProps}
              className={clsx(
                "grid gap-x-4 gap-y-0.5 items-center",
                showSource
                  ? "grid-cols-[1fr_auto] sm:grid-cols-[1fr_auto_4.5rem]"
                  : "grid-cols-[1fr_auto]",
                isPage ? "py-2.5 border-b border-line/30 last:border-b-0" : "px-3 py-2.5",
                linkDerivation && "hover:bg-surface-2/40 transition-colors cursor-pointer",
              )}
            >
              <span
                className={clsx("text-ink-mute truncate", isPage ? "text-sm" : "text-xs")}
                title={m.name}
              >
                {m.name}
              </span>
              <span
                className={clsx(
                  "num font-semibold text-ink tabular-nums text-right",
                  isPage ? "text-base" : "text-sm",
                )}
              >
                {formatted}
              </span>
              {showSource && (
                <>
                  <span className="hidden sm:block text-right">
                    <EvidenceInlineLinks items={rowEvidence} />
                  </span>
                  {rowEvidence.length > 0 && (
                    <span className="sm:hidden col-span-2 text-right -mt-0.5">
                      <EvidenceInlineLinks items={rowEvidence} />
                    </span>
                  )}
                </>
              )}
            </Tag>
          );
        })}
      </div>
    </>
  );
}

function MetricSection({
  title,
  description,
  rows,
  evidence,
  showSource,
  linkDerivation,
  isPage,
}: {
  title: string;
  description?: string;
  rows: IOMetric[];
  evidence: EvidenceItem[];
  showSource: boolean;
  linkDerivation: boolean;
  isPage: boolean;
}) {
  if (rows.length === 0) return null;

  return (
    <div className={clsx(isPage && "pb-4 last:pb-1")}>
      <div className={clsx("mb-2", isPage ? "pt-3 first:pt-1" : undefined)}>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-soft">{title}</h3>
        {description && <p className="text-[11px] text-ink-mute mt-0.5">{description}</p>}
      </div>
      <MetricRows
        rows={rows}
        evidence={evidence}
        showSource={showSource}
        linkDerivation={linkDerivation}
        isPage={isPage}
      />
    </div>
  );
}

export function KeyMetricsPanel({
  metrics,
  evidence,
  calculationChain,
  subtitle,
  variant = "page",
  className,
}: Props) {
  if (metrics.length === 0) return null;

  const isPage = variant === "page";
  const { extracted, computed } = partitionMetrics(metrics, evidence);

  return (
    <section className={clsx(isPage ? "card overflow-hidden" : undefined, className)}>
      <div
        className={clsx(
          "flex items-center justify-between gap-3",
          isPage ? "px-5 py-4 border-b border-line/60" : "mb-2",
        )}
      >
        <div className="min-w-0">
          {isPage ? (
            <>
              <h2 className="text-base font-semibold">Key metrics</h2>
              {subtitle && <p className="text-xs text-ink-soft mt-0.5">{subtitle}</p>}
            </>
          ) : (
            <h3 className="text-xs uppercase tracking-wider text-ink-soft">Key metrics</h3>
          )}
        </div>
        {calculationChain && computed.length > 0 && (
          <a
            href={`#${CALCULATION_CHAIN_ANCHOR}`}
            className="text-xs text-ink-soft hover:text-ink shrink-0"
            title="See formula + sources"
          >
            Show derivation
          </a>
        )}
      </div>

      <div className={clsx(isPage ? "px-5 py-1 divide-y divide-line/40" : undefined)}>
        <MetricSection
          title="Extracted from filing"
          description="Values read directly from the source document."
          rows={extracted}
          evidence={evidence}
          showSource
          linkDerivation={false}
          isPage={isPage}
        />
        <MetricSection
          title="Computed metrics"
          description="Derived from extracted inputs using catalog formulas."
          rows={computed}
          evidence={evidence}
          showSource={false}
          linkDerivation={Boolean(calculationChain)}
          isPage={isPage}
        />
      </div>
    </section>
  );
}
