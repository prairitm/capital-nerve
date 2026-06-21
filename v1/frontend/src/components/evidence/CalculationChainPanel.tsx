import type { ReactNode } from "react";
import clsx from "clsx";
import { AlertTriangle } from "lucide-react";
import type {
  CalculationChain,
  CalculationChainInput,
  CalculationChainMetric,
  CalculationChainSignal,
  SignalDirection,
} from "@/api/types";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import { formatMetricValue } from "@/lib/format";

interface Props {
  chain: CalculationChain | null | undefined;
  className?: string;
}

function operatorLabel(op: string | null | undefined): string {
  switch (op) {
    case ">":
      return ">";
    case ">=":
      return "≥";
    case "<":
      return "<";
    case "<=":
      return "≤";
    case "==":
      return "=";
    case "!=":
      return "≠";
    default:
      return op ?? "";
  }
}

function scopeLabel(scope: string | null | undefined): string {
  switch ((scope ?? "").toUpperCase()) {
    case "CURRENT":
      return "Current period";
    case "PQ":
      return "Prior quarter";
    case "PY":
      return "Prior year";
    case "PY_PQ":
      return "Prior year prior quarter";
    case "TTM":
      return "TTM sum";
    case "TTM_AVG":
      return "TTM avg";
    case "AVG_2_OPENING_CLOSING":
      return "Opening / closing avg";
    default:
      return scope ?? "";
  }
}

function valueTone(direction: SignalDirection | null | undefined): string {
  switch (direction) {
    case "POSITIVE":
      return "text-positive";
    case "NEGATIVE":
      return "text-negative";
    case "MIXED":
      return "text-mixed";
    default:
      return "text-ink";
  }
}

function splitRuleText(text: string): { headline: string; notation: string | null } {
  const match = text.match(/^(.+?)\s*(\([^)]+\))\s*$/);
  if (match) {
    return { headline: match[1].trim(), notation: match[2] };
  }
  return { headline: text, notation: null };
}

function splitFormulaExpression(formulaText: string): string {
  const eqIdx = formulaText.lastIndexOf("=");
  return eqIdx !== -1 ? formulaText.slice(0, eqIdx).trim() : formulaText;
}

function observedValue(
  signal: CalculationChainSignal | null | undefined,
  metric: CalculationChainMetric | null | undefined,
): string | null {
  const unit = signal?.fired_unit ?? metric?.unit ?? null;
  if (signal?.fired_value !== null && signal?.fired_value !== undefined) {
    return formatMetricValue(signal.fired_value, unit);
  }
  if (metric?.value !== null && metric?.value !== undefined) {
    return formatMetricValue(metric.value, metric.unit);
  }
  return null;
}

function buildTriggerSummary(
  signal: CalculationChainSignal,
  metric: CalculationChainMetric | null | undefined,
): string | null {
  const metricLabel = metric?.name ?? signal.metric_ref?.replace(/_/g, " ") ?? "this metric";
  const observed = observedValue(signal, metric);

  if (signal.operator && signal.threshold !== null) {
    const threshold = formatMetricValue(
      signal.threshold,
      signal.fired_unit ?? metric?.unit ?? null,
    );
    return observed
      ? `Triggered because ${metricLabel} (${observed}) ${operatorLabel(signal.operator)} ${threshold}.`
      : `Triggered when ${metricLabel} ${operatorLabel(signal.operator)} ${threshold}.`;
  }

  if (signal.rule_text) {
    const { headline } = splitRuleText(signal.rule_text);
    if (observed && headline) {
      return `${headline} (${observed}).`;
    }
    return headline || null;
  }

  return null;
}

function StepLabel({ step, label }: { step: number; label: string }) {
  return (
    <div className="mb-3.5 flex items-center gap-2.5">
      <span
        className="flex size-5 shrink-0 items-center justify-center rounded-md border border-line/60 bg-surface-3 text-[10px] font-semibold text-ink-mute tabular-nums"
        aria-hidden
      >
        {step}
      </span>
      <span className="text-[11px] font-medium uppercase tracking-wider text-ink-soft">
        {label}
      </span>
    </div>
  );
}

function TriggerFootnote({
  signal,
  metric,
}: {
  signal: CalculationChainSignal;
  metric: CalculationChainMetric | null | undefined;
}) {
  const summary = buildTriggerSummary(signal, metric);
  if (!summary) return null;

  return (
    <p className="mt-2 text-xs leading-relaxed text-ink-mute border-l-2 border-line pl-3">
      {summary}
    </p>
  );
}

function MetricBlock({
  metric,
  signal,
}: {
  metric: CalculationChainMetric;
  signal: CalculationChainSignal | null | undefined;
}) {
  const result =
    metric.value !== null ? formatMetricValue(metric.value, metric.unit) : null;
  const expression = metric.formula_text ? splitFormulaExpression(metric.formula_text) : "";

  return (
    <div className="space-y-3.5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-0.5">
          {metric.name && (
            <h3 className="text-sm font-semibold leading-snug text-ink">{metric.name}</h3>
          )}
          {metric.code && (
            <p className="font-mono text-[11px] text-ink-soft">{metric.code}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-start gap-2">
          {result && (
            <div
              className={clsx(
                "num text-2xl font-semibold tabular-nums leading-none",
                valueTone(signal?.direction),
              )}
            >
              {result}
            </div>
          )}
          {metric.is_quarantined && (
            <span
              className="chip-mixed text-[11px]"
              title="Value outside the metric's plausible range — not used for signals."
            >
              <AlertTriangle size={11} /> Quarantined
            </span>
          )}
        </div>
      </div>

      {expression && (
        <div className="rounded-xl border border-line/50 bg-surface px-3.5 py-3">
          <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-ink-soft">
            Formula
          </div>
          <code className="break-all font-mono text-xs leading-relaxed text-ink-mute">
            {expression}
          </code>
        </div>
      )}

      {metric.is_quarantined && metric.quarantine_reason && (
        <p className="border-l-2 border-mixed pl-3 text-xs leading-relaxed text-ink-mute">
          {metric.quarantine_reason}
        </p>
      )}
    </div>
  );
}

function InputRow({ input }: { input: CalculationChainInput }) {
  const value = formatMetricValue(input.value, input.unit);
  const label = input.code ? input.code.replace(/_/g, " ") : input.formula_name;
  const kindLabel = input.kind === "metric" ? "Calculated" : "Fact";

  return (
    <div className="space-y-2 py-3 first:pt-0 last:pb-0">
      <div className="grid grid-cols-[1fr_auto] items-baseline gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <div className="truncate text-sm text-ink" title={label}>
            {label}
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-ink-soft">{input.formula_name}</div>
        </div>
        <div className="hidden text-xs text-ink-mute sm:block">
          {scopeLabel(input.scope)}
          <span className="text-ink-soft"> · </span>
          {kindLabel}
        </div>
        <div className="num text-right text-sm font-semibold tabular-nums text-ink">{value}</div>
        <div className="col-span-2 text-[11px] text-ink-soft sm:hidden">
          {scopeLabel(input.scope)} · {kindLabel}
        </div>
      </div>
      {input.source_text && (
        <blockquote className="border-l-2 border-line pl-3 text-[11px] italic leading-snug text-ink-mute">
          &ldquo;{input.source_text.trim()}&rdquo;
        </blockquote>
      )}
      {input.document_id != null && (
        <div className="text-[11px]">
          <SourceDocumentLink
            documentId={input.document_id}
            page={input.page_number ?? undefined}
            label={input.page_number != null ? `Open p.${input.page_number}` : "Open source"}
            className="text-[11px] font-normal"
          />
        </div>
      )}
    </div>
  );
}

function InputsBlock({ inputs }: { inputs: CalculationChainInput[] }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <span className="text-[11px] text-ink-soft">
          {inputs.length} variable{inputs.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="hidden gap-3 border-b border-line/40 px-1 pb-2 text-[10px] font-medium uppercase tracking-wider text-ink-soft sm:grid sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]">
        <span>Variable</span>
        <span>Period</span>
        <span className="text-right">Value</span>
      </div>
      <div className="divide-y divide-line/30">
        {inputs.map((input, index) => (
          <InputRow key={`${input.formula_name}-${input.scope}-${index}`} input={input} />
        ))}
      </div>
    </div>
  );
}

/** DOM id of the "Why this fired" anchor. Metric cells elsewhere on the
 *  page (IO page, drawer, financial-context table) use this id to scroll
 *  the user into the calculation chain. */
export const CALCULATION_CHAIN_ANCHOR = "why-fired";

/**
 * "Why it fired" panel — metric-first derivation chain (Metric → Inputs).
 *
 * Signal metadata is folded into a one-line footnote under the header; the
 * page hero already carries signal name, category, and direction. Designed to
 * sit above the existing "How we computed this" collapsible.
 */
export function CalculationChainPanel({ chain, className }: Props) {
  if (!chain || (!chain.signal && !chain.metric)) return null;

  const metric = chain.metric;
  const signal = chain.signal;
  const inputs = metric?.inputs ?? [];

  const sections: { label: string; content: ReactNode }[] = [];
  if (metric) {
    sections.push({
      label: "Trigger metric",
      content: <MetricBlock metric={metric} signal={signal} />,
    });
  }
  if (inputs.length > 0) {
    sections.push({ label: "Source inputs", content: <InputsBlock inputs={inputs} /> });
  }

  return (
    <section
      id={CALCULATION_CHAIN_ANCHOR}
      className={clsx("card scroll-mt-24 p-5 md:p-6", className)}
    >
      <header className="mb-5">
        <h2 className="text-base font-semibold text-ink">Why this fired</h2>
        <p className="mt-1 text-xs leading-relaxed text-ink-soft">
          The computed value, formula, and source figures behind this card.
        </p>
        {signal && <TriggerFootnote signal={signal} metric={metric} />}
      </header>

      {sections.length > 0 ? (
        <div className="overflow-hidden rounded-2xl border border-line/60 divide-y divide-line/40">
          {sections.map(({ label, content }, index) => (
            <div key={label} className="bg-surface-2/20 p-4 md:p-5">
              <StepLabel step={index + 1} label={label} />
              {content}
            </div>
          ))}
        </div>
      ) : signal ? (
        <p className="text-sm text-ink-mute">{buildTriggerSummary(signal, metric)}</p>
      ) : null}
    </section>
  );
}
