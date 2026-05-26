import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type {
  MetricKind,
  MetricRegistryEntry,
  MetricRegistryResponse,
} from "@/api/types";
import { MetricKindBadge } from "@/components/common/MetricKindBadge";

interface Props {
  open: boolean;
  initialMetricCode?: string | null;
  onClose: () => void;
}

const KIND_ORDER: MetricKind[] = ["financial", "composite", "model_score"];

function formatBound(value: number | null, unit: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (unit === "%") return `${value.toFixed(1)}%`;
  if (unit === "bps") return `${value.toFixed(0)} bps`;
  if (unit === "pp") return `${value.toFixed(1)} pp`;
  if (unit === "score") return `${value.toFixed(0)} / 100`;
  if (unit === "x") return `${value.toFixed(2)}x`;
  return value.toFixed(2);
}

/**
 * Read-only catalog of every metric the pipeline knows about. Reached from
 * the analyst-trust strip on any feed row ("Definition") or from a
 * top-level shell affordance. The shape mirrors `/v1/metrics/registry` so
 * the drawer never has to derive metric metadata client-side.
 */
export function MetricRegistryDrawer({ open, initialMetricCode, onClose }: Props) {
  const [selected, setSelected] = useState<string | null>(initialMetricCode ?? null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (initialMetricCode) setSelected(initialMetricCode);
  }, [initialMetricCode]);

  const registry = useQuery({
    queryKey: ["metric-registry"],
    queryFn: () => api<MetricRegistryResponse>("/v1/metrics/registry"),
    enabled: open,
    staleTime: 5 * 60_000,
  });

  const grouped = useMemo(() => {
    const groups: Record<MetricKind, MetricRegistryEntry[]> = {
      financial: [],
      composite: [],
      model_score: [],
    };
    const haystack = query.trim().toLowerCase();
    for (const m of registry.data?.metrics ?? []) {
      if (haystack) {
        const hit =
          m.metric_code.toLowerCase().includes(haystack) ||
          m.metric_name.toLowerCase().includes(haystack) ||
          m.metric_category.toLowerCase().includes(haystack);
        if (!hit) continue;
      }
      groups[m.metric_kind].push(m);
    }
    return groups;
  }, [registry.data, query]);

  const detail = useMemo(() => {
    if (!selected || !registry.data) return null;
    return registry.data.metrics.find((m) => m.metric_code === selected) ?? null;
  }, [registry.data, selected]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex" role="dialog" aria-modal="true">
      <button
        type="button"
        onClick={onClose}
        className="flex-1 bg-black/40"
        aria-label="Close metric registry"
      />
      <aside className="relative h-full w-full max-w-3xl overflow-hidden bg-surface shadow-2xl flex flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-line/60 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">Metric registry</h2>
            <p className="text-xs text-ink-soft">
              Every metric the pipeline computes, with its formula, range, inputs, and downstream signals.
            </p>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost px-2 py-1" title="Close">
            <X size={16} />
          </button>
        </header>

        <div className="flex flex-1 min-h-0">
          <div className="w-72 border-r border-line/60 overflow-y-auto p-3 shrink-0">
            <div className="relative mb-3">
              <Search size={14} className="absolute left-2 top-2 text-ink-soft" />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search metric code or name"
                className="input pl-7"
              />
            </div>
            {registry.isLoading && (
              <p className="text-xs text-ink-soft px-2 py-1">Loading…</p>
            )}
            {registry.isError && (
              <p className="text-xs text-negative px-2 py-1">Could not load registry.</p>
            )}
            {KIND_ORDER.map((kind) => {
              const list = grouped[kind];
              if (!list.length) return null;
              return (
                <section key={kind} className="mb-4">
                  <div className="flex items-center gap-2 mb-1.5">
                    <MetricKindBadge kind={kind} />
                    <span className="text-[11px] text-ink-soft">{list.length}</span>
                  </div>
                  <ul className="space-y-0.5">
                    {list.map((m) => (
                      <li key={m.metric_code}>
                        <button
                          type="button"
                          onClick={() => setSelected(m.metric_code)}
                          className={clsx(
                            "w-full text-left px-2 py-1 rounded-md hover:bg-surface-2",
                            selected === m.metric_code && "bg-surface-2",
                          )}
                        >
                          <div className="text-sm text-ink truncate">{m.metric_name}</div>
                          <div className="text-[11px] text-ink-soft truncate font-mono">
                            {m.metric_code}
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>

          <div className="flex-1 overflow-y-auto p-5 min-w-0">
            {detail ? (
              <article className="space-y-5">
                <header>
                  <div className="flex items-center gap-2">
                    <MetricKindBadge kind={detail.metric_kind} />
                    <span className="text-[11px] text-ink-soft capitalize">
                      {detail.metric_category.replace(/_/g, " ")}
                    </span>
                  </div>
                  <h3 className="text-xl font-semibold text-ink mt-1">{detail.metric_name}</h3>
                  <p className="text-xs font-mono text-ink-soft mt-0.5">{detail.metric_code}</p>
                </header>

                {detail.formula_text && (
                  <section>
                    <h4 className="text-xs uppercase tracking-wider text-ink-soft mb-1">Formula</h4>
                    <code className="block rounded-md bg-surface-2 px-3 py-2 text-sm font-mono text-ink leading-relaxed">
                      {detail.formula_text}
                    </code>
                  </section>
                )}

                <section className="grid grid-cols-2 gap-3 text-xs">
                  <div className="card-2 p-3">
                    <div className="text-[11px] text-ink-soft mb-1">Expected range</div>
                    <div className="text-sm font-medium text-ink">
                      {formatBound(detail.validation_min, detail.unit)} —{" "}
                      {formatBound(detail.validation_max, detail.unit)}
                    </div>
                    <div className="text-[11px] text-ink-soft mt-1">
                      Values outside this range are quarantined and never feed signals.
                    </div>
                  </div>
                  <div className="card-2 p-3">
                    <div className="text-[11px] text-ink-soft mb-1">Unit</div>
                    <div className="text-sm font-medium text-ink">{detail.unit ?? "—"}</div>
                  </div>
                </section>

                {detail.inputs.length > 0 && (
                  <section>
                    <h4 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Inputs</h4>
                    <ul className="card-2 divide-y divide-line/40">
                      {detail.inputs.map((i) => (
                        <li key={i.name} className="px-3 py-2 text-sm flex items-baseline justify-between gap-3">
                          <div>
                            <span className="font-mono text-ink-mute">{i.name}</span>
                            {i.code && <span className="text-ink-soft ml-2">= {i.code}</span>}
                          </div>
                          <span className="text-[11px] text-ink-soft">
                            {i.kind} · {i.scope}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {detail.dependencies.length > 0 && (
                  <section>
                    <h4 className="text-xs uppercase tracking-wider text-ink-soft mb-2">Depends on</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {detail.dependencies.map((dep) => (
                        <button
                          key={dep}
                          type="button"
                          onClick={() => setSelected(dep)}
                          className="chip-low text-[11px] hover:bg-surface-2"
                        >
                          {dep}
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                {detail.related_signals.length > 0 && (
                  <section>
                    <h4 className="text-xs uppercase tracking-wider text-ink-soft mb-2">
                      Related signals
                    </h4>
                    <ul className="card-2 divide-y divide-line/40">
                      {detail.related_signals.map((s) => (
                        <li key={s.signal_code} className="px-3 py-2 text-sm">
                          <div className="text-ink">{s.signal_name}</div>
                          {s.rule_text && (
                            <div className="text-[11px] font-mono text-ink-mute mt-0.5">
                              {s.rule_text}
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </article>
            ) : (
              <p className="text-sm text-ink-soft">Pick a metric on the left to see its definition.</p>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
