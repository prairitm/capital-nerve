import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { SeverityLevel, Signal, SignalDirection } from "@/api/types";
import { SignalTable } from "@/components/signals/SignalTable";
import { ErrorState, PageHeader, PageSkeleton, StatusSummary } from "@/components/common/DashboardUI";

export function Signals() {
  const [params, setParams] = useSearchParams();
  const category = params.get("category") || "";
  const severity = (params.get("severity") || "") as SeverityLevel | "";
  const direction = (params.get("direction") || "") as SignalDirection | "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  const clearFilters = () => setParams(new URLSearchParams());

  const signalQuery = useQuery({
    queryKey: ["signals", category, severity, direction],
    queryFn: () =>
      api<Signal[]>("/signals", {
        query: { category, severity, direction, limit: 200 },
      }),
  });
  const { data, isLoading } = signalQuery;

  if (isLoading) return <PageSkeleton rows={5} />;
  if (signalQuery.isError) return <ErrorState onRetry={() => void signalQuery.refetch()} />;

  const signals = data ?? [];
  const highPriority = signals.filter((s) => s.severity === "HIGH" || s.severity === "CRITICAL").length;
  const positive = signals.filter((s) => s.direction === "POSITIVE").length;
  const negative = signals.filter((s) => s.direction === "NEGATIVE").length;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader eyebrow="Signal registry" title="Material intelligence" description="Detected financial and operational developments across all covered companies." />

      <StatusSummary items={[
        { label: "Results", value: signals.length, hint: category || severity || direction ? "Matching active filters" : "All available signals" },
        { label: "High priority", value: highPriority, hint: "Critical and high materiality", tone: highPriority ? "warning" : "default" },
        { label: "Positive", value: positive, hint: "Constructive developments", tone: "positive" },
        { label: "Negative", value: negative, hint: "Adverse developments", tone: "negative" },
      ]} />

      <SignalTable
          signals={signals}
          showCompany
          showSeverity
          groupByDocumentType
          filters={{
            category,
            severity,
            direction,
            onCategoryChange: (value) => setParam("category", value),
            onSeverityChange: (value) => setParam("severity", value),
            onDirectionChange: (value) => setParam("direction", value),
            onClear: clearFilters,
          }}
        />
    </div>
  );
}
