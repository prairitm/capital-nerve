import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { FinancialTrend } from "@/api/types";
import { Spinner } from "@/components/common/Spinner";
import { formatNumber, formatPct } from "@/lib/format";

interface Props {
  symbol: string;
  /** Comma-separated metric codes (defaults to the analyst signal set on the backend). */
  codes?: string[];
  quarters?: number;
  className?: string;
}

const SERIES_COLORS = ["#60A5FA", "#34D399", "#F59E0B", "#F87171", "#A78BFA", "#22D3EE"];

interface ChartDatum {
  period_label: string;
  period_end_date: string;
  [metricCode: string]: number | string | null;
}

function buildChartData(trends: FinancialTrend[]): ChartDatum[] {
  const periodMap = new Map<string, ChartDatum>();
  for (const trend of trends) {
    for (const point of trend.points) {
      const key = point.period_end_date;
      let row = periodMap.get(key);
      if (!row) {
        row = {
          period_label: point.period_label,
          period_end_date: point.period_end_date,
        };
        periodMap.set(key, row);
      }
      row[trend.metric_code] = point.value;
    }
  }
  return Array.from(periodMap.values()).sort(
    (a, b) => new Date(a.period_end_date).getTime() - new Date(b.period_end_date).getTime(),
  );
}

function formatTooltipValue(value: number | null, unit: string): string {
  if (value == null) return "—";
  if (unit === "%") return formatPct(value, 1);
  if (unit === "bps") return `${value >= 0 ? "+" : ""}${value.toFixed(0)} bps`;
  return formatNumber(value, 2);
}

/**
 * Multi-line "Signal trend" chart on the company hub. Renders the last N
 * quarters of analyst-relevant calculated metrics so an analyst can see
 * direction-of-travel for revenue growth, EBITDA margin, PAT margin, and
 * segment margin without leaving the company page.
 */
export function SignalTrendChart({
  symbol,
  codes,
  quarters = 8,
  className,
}: Props) {
  const codesParam = codes?.join(",");
  const { data, isLoading } = useQuery({
    queryKey: ["company-metric-trend", symbol, codesParam ?? "default", quarters],
    queryFn: () => {
      const params = new URLSearchParams();
      if (codesParam) params.set("codes", codesParam);
      params.set("quarters", String(quarters));
      return api<FinancialTrend[]>(
        `/v1/companies/${symbol}/metric-trend?${params.toString()}`,
      );
    },
    enabled: !!symbol,
  });

  const chartData = useMemo(() => (data ? buildChartData(data) : []), [data]);

  if (isLoading) {
    return (
      <section className={className}>
        <div className="card p-5 flex items-center gap-2 text-ink-mute text-sm">
          <Spinner /> Loading signal trend…
        </div>
      </section>
    );
  }

  if (!data || data.length === 0 || chartData.length === 0) return null;

  return (
    <section className={className}>
      <div className="card p-5 md:p-6">
        <header className="flex items-baseline justify-between gap-3 mb-3">
          <div>
            <h2 className="text-base font-semibold">Signal trend</h2>
            <p className="text-xs text-ink-soft mt-0.5">
              Last {quarters} quarters of growth, margin, and segment quality.
            </p>
          </div>
        </header>

        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1F2937" strokeDasharray="3 3" />
              <XAxis
                dataKey="period_label"
                tick={{ fill: "#94A3B8", fontSize: 10 }}
                axisLine={{ stroke: "#1F2937" }}
                tickLine={{ stroke: "#1F2937" }}
              />
              <YAxis
                tick={{ fill: "#94A3B8", fontSize: 10 }}
                axisLine={{ stroke: "#1F2937" }}
                tickLine={{ stroke: "#1F2937" }}
                width={42}
                tickFormatter={(v: number) => (v % 1 === 0 ? `${v}` : v.toFixed(1))}
              />
              <Tooltip
                contentStyle={{
                  background: "#141A26",
                  border: "1px solid #222B3D",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(value: number, name: string) => {
                  const trend = data.find((t) => t.metric_name === name);
                  return formatTooltipValue(value, trend?.unit ?? "");
                }}
                labelStyle={{ color: "#E2E8F0", marginBottom: 4 }}
              />
              <Legend
                wrapperStyle={{ paddingTop: 8, fontSize: 11, color: "#94A3B8" }}
                iconType="line"
              />
              {data.map((trend, idx) => (
                <Line
                  key={trend.metric_code}
                  type="monotone"
                  dataKey={trend.metric_code}
                  name={trend.metric_name}
                  stroke={SERIES_COLORS[idx % SERIES_COLORS.length]}
                  strokeWidth={1.75}
                  dot={{ r: 2 }}
                  activeDot={{ r: 4 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
