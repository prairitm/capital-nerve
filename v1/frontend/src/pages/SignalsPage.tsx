import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "@/api/client";
import type { SeverityLevel, SignalBriefV1, SignalDirection } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";

const CATEGORIES = [
  { value: "", label: "All" },
  { value: "growth", label: "Growth" },
  { value: "margin", label: "Margin" },
  { value: "profit_quality", label: "Profit Quality" },
  { value: "expense", label: "Expense" },
  { value: "red_flag", label: "Red Flags" },
  { value: "management", label: "Management" },
];

const SEVERITIES: { value: SeverityLevel | ""; label: string }[] = [
  { value: "", label: "Any severity" },
  { value: "LOW", label: "Low" },
  { value: "MEDIUM", label: "Medium" },
  { value: "HIGH", label: "High" },
  { value: "CRITICAL", label: "Critical" },
];

const DIRECTIONS: { value: SignalDirection | ""; label: string }[] = [
  { value: "", label: "Any direction" },
  { value: "POSITIVE", label: "Positive" },
  { value: "NEGATIVE", label: "Negative" },
  { value: "MIXED", label: "Mixed" },
];

export function SignalsPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const category = params.get("category") || "";
  const severity = (params.get("severity") || "") as SeverityLevel | "";
  const direction = (params.get("direction") || "") as SignalDirection | "";

  const { data, isLoading } = useQuery({
    queryKey: ["signals", category, severity, direction],
    queryFn: () =>
      api<SignalBriefV1[]>("/v1/signals", {
        query: { category, severity, direction },
      }),
  });

  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next);
  };

  const openSignal = (signalId: number) => navigate(`/signals/${signalId}`);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Signals</h1>
        <p className="text-sm text-ink-mute">Discover companies by signal, not by raw numbers.</p>
      </div>

      <div className="card p-3 flex flex-col sm:flex-row sm:flex-wrap gap-3">
        <div className="flex flex-wrap gap-1.5 min-w-0">
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              onClick={() => setParam("category", c.value)}
              className={clsx(
                "px-2.5 py-1 text-xs rounded-full border whitespace-nowrap",
                category === c.value
                  ? "btn-brand-active"
                  : "border-line text-ink-mute hover:text-ink hover:bg-surface",
              )}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row sm:ml-auto gap-2 w-full sm:w-auto">
          <select
            value={severity}
            onChange={(e) => setParam("severity", e.target.value)}
            className="input w-full sm:min-w-[10rem]"
          >
            {SEVERITIES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <select
            value={direction}
            onChange={(e) => setParam("direction", e.target.value)}
            className="input w-full sm:min-w-[10rem]"
          >
            {DIRECTIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <PageLoader />
      ) : !data || data.length === 0 ? (
        <div className="card p-8 text-sm text-ink-mute text-center">No signals match these filters.</div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="card hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink-soft border-b border-line/60">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Company</th>
                  <th className="px-4 py-3 text-left font-medium">Signal</th>
                  <th className="px-4 py-3 text-left font-medium">Category</th>
                  <th className="px-4 py-3 text-left font-medium">Severity</th>
                  <th className="px-4 py-3 text-left font-medium">Direction</th>
                  <th className="px-4 py-3 text-left font-medium">Period</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <tr
                    key={r.signal_id}
                    onClick={() => openSignal(r.signal_id)}
                    className="border-b border-line/30 hover:bg-surface-2/50 cursor-pointer"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium">{r.company?.company_name ?? "—"}</div>
                      <div className="text-[11px] text-ink-soft">
                        {r.company?.nse_symbol} · {r.company?.sector_name}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium">{r.signal_name}</div>
                      <div className="text-[11px] text-ink-mute line-clamp-1">{r.explanation}</div>
                    </td>
                    <td className="px-4 py-3 text-ink-mute capitalize">
                      {r.signal_category.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge level={r.severity} />
                    </td>
                    <td className="px-4 py-3">
                      <SignalBadge direction={r.direction} />
                    </td>
                    <td className="px-4 py-3 text-ink-mute">{r.period?.display_label || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden grid grid-cols-1 gap-2">
            {data.map((r) => (
              <button
                key={r.signal_id}
                onClick={() => openSignal(r.signal_id)}
                className="card p-4 text-left w-full"
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-sm font-semibold">
                    {r.company?.short_name || r.company?.company_name || "—"}
                  </span>
                  <SignalBadge direction={r.direction} />
                </div>
                <div className="text-sm">{r.signal_name}</div>
                <div className="text-[11px] text-ink-soft mt-1 line-clamp-2">{r.explanation}</div>
                <div className="flex items-center justify-between mt-2 text-[11px] text-ink-soft">
                  <SeverityBadge level={r.severity} />
                  <span>{r.period?.display_label || ""}</span>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
