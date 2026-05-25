import clsx from "clsx";
import { AlertTriangle } from "lucide-react";
import type {
  CalculationChain,
  CalculationChainInput,
  CalculationChainSignal,
} from "@/api/types";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import { formatNumber, formatPct, formatSigned } from "@/lib/format";

interface Props {
  chain: CalculationChain | null | undefined;
  className?: string;
}

function formatValueWithUnit(
  value: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (unit === "%") return formatPct(value, 1);
  if (unit === "bps") return formatSigned(value, 0, " bps");
  if (unit === "x") return `${formatNumber(value, 2)}x`;
  if (unit === "crore") return `${formatNumber(value, value < 100 ? 2 : 0)} Cr`;
  if (unit === "Rs") return `Rs ${formatNumber(value, 2)}`;
  if (unit === "days") return `${formatNumber(value, 0)} days`;
  if (unit) return `${formatNumber(value, 2)} ${unit}`;
  return formatNumber(value, 2);
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

function SignalRow({ signal }: { signal: CalculationChainSignal }) {
  const fired = formatValueWithUnit(signal.fired_value, signal.fired_unit);
  const threshold =
    signal.metric_ref
      ? signal.metric_ref
      : signal.threshold !== null
        ? formatValueWithUnit(signal.threshold, signal.fired_unit)
        : null;

  return (
    <div className="card-2 p-4 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[11px] uppercase tracking-wider text-ink-soft">Signal</div>
        {signal.category && (
          <span className="text-[11px] text-ink-soft capitalize">
            {signal.category.replace(/_/g, " ")}
          </span>
        )}
      </div>
      {signal.name && (
        <div className="text-sm font-medium text-ink leading-snug">{signal.name}</div>
      )}
      {signal.rule_text && (
        <div className="text-xs font-mono text-ink-mute bg-surface-2/60 rounded-md px-2 py-1.5 leading-relaxed">
          {signal.rule_text}
        </div>
      )}
      {(signal.fired_value !== null || threshold) && (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-ink-mute">
          <span>Observed</span>
          <span className="num font-semibold text-ink">{fired}</span>
          {signal.operator && threshold && (
            <>
              <span className="text-ink-soft">vs rule</span>
              <span className="num text-ink">
                {operatorLabel(signal.operator)} {threshold}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function InputRow({ input }: { input: CalculationChainInput }) {
  const value = formatValueWithUnit(input.value, input.unit);
  return (
    <div className="flex flex-col gap-1 border-t border-line/40 first:border-t-0 py-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-medium text-ink truncate">
            <span className="font-mono text-ink-mute">{input.formula_name}</span>
            {input.code && (
              <span className="ml-2 text-ink-soft">
                = {input.code.replace(/_/g, " ")}
              </span>
            )}
          </div>
          <div className="text-[11px] text-ink-soft mt-0.5">
            {scopeLabel(input.scope)} · {input.kind === "metric" ? "Calculated metric" : "Fact"}
          </div>
        </div>
        <div className="num text-sm font-semibold text-ink shrink-0">{value}</div>
      </div>
      {input.source_text && (
        <p className="text-[11px] text-ink-mute italic border-l-2 border-line pl-2 leading-snug">
          “{input.source_text.trim()}”
        </p>
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

/**
 * "Why it fired" panel — renders the structured Signal → Metric → Inputs chain.
 *
 * Designed to sit above the existing "How we computed this" collapsible. The
 * chain payload is built once on the backend in
 * `services/intelligence_object_builder._build_calculation_chain` so this
 * panel never needs more than one API response.
 */
export function CalculationChainPanel({ chain, className }: Props) {
  if (!chain || (!chain.signal && !chain.metric)) return null;

  const metric = chain.metric;
  const signal = chain.signal;
  const inputs = metric?.inputs ?? [];

  return (
    <section className={clsx("card p-5 md:p-6 space-y-4", className)}>
      <header>
        <h2 className="text-base font-semibold">Why this fired</h2>
        <p className="text-xs text-ink-soft mt-0.5">
          The exact rule, formula, and source values behind this card.
        </p>
      </header>

      {signal && <SignalRow signal={signal} />}

      {metric && (
        <div className="card-2 p-4 space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">Metric</div>
            {metric.is_quarantined && (
              <span
                className="chip-mixed text-[11px]"
                title="Value outside the metric's plausible range — not used for signals."
              >
                <AlertTriangle size={11} /> Quarantined
              </span>
            )}
          </div>
          {metric.name && (
            <div className="text-sm font-medium text-ink leading-snug">{metric.name}</div>
          )}
          {metric.formula_text && (
            <div className="text-xs font-mono text-ink-mute bg-surface-2/60 rounded-md px-2 py-1.5 leading-relaxed">
              {metric.formula_text}
              {metric.value !== null && (
                <span className="text-ink ml-1.5 font-semibold num">
                  = {formatValueWithUnit(metric.value, metric.unit)}
                </span>
              )}
            </div>
          )}
          {metric.is_quarantined && metric.quarantine_reason && (
            <p className="text-xs text-ink-mute leading-relaxed">{metric.quarantine_reason}</p>
          )}
        </div>
      )}

      {inputs.length > 0 && (
        <div className="card-2 p-4">
          <div className="flex items-baseline justify-between gap-3 mb-1">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">Inputs</div>
            <span className="text-[11px] text-ink-soft">{inputs.length} variable{inputs.length === 1 ? "" : "s"}</span>
          </div>
          <div>
            {inputs.map((input) => (
              <InputRow key={input.formula_name} input={input} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
