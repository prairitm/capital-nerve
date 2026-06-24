import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { SeverityLevel, Signal, SignalDirection } from "@/api/types";
import { SignalTable } from "@/components/signals/SignalTable";
import { PageLoader } from "@/components/common/Spinner";

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

  const { data, isLoading } = useQuery({
    queryKey: ["signals", category, severity, direction],
    queryFn: () =>
      api<Signal[]>("/signals", {
        query: { category, severity, direction, limit: 200 },
      }),
  });

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-ink">Signals</h1>
        <p className="text-sm text-ink-mute mt-0.5">
          Every signal the pipeline fired across companies.
        </p>
      </div>

      {isLoading ? (
        <PageLoader />
      ) : (
        <SignalTable
          signals={data ?? []}
          showCompany
          showSeverity
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
      )}
    </div>
  );
}
