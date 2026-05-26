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
  [key: string]: number | string | boolean | null;
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
      row[`${trend.metric_code}__anomaly`] = Boolean(point.anomaly_flag);
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

function formatBandValue(value: number | null | undefined, unit: string): string {
  if (value == null) return "—";
  if (unit === "%") return formatPct(value, 1);
  return formatNumber(value, 1);
}

function AnomalyDot({
  cx,
  cy,
  stroke,
  payload,
  dataKey,
}: {
  cx?: number;
  cy?: number;
  stroke?: string;
  payload?: ChartDatum;
  dataKey?: string | number;
}) {
  if (cx == null || cy == null || !dataKey) return null;
  const code = String(dataKey);
  const flagged = payload?.[`${code}__anomaly`] === true;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={flagged ? 4 : 2}
      fill={flagged ? "#F59E0B" : stroke}
      stroke={flagged ? "#F59E0B" : stroke}
      strokeWidth={flagged ? 2 : 0}
    />
  );
}

/**
 * Multi-line "Signal trend" chart on the company hub. Renders the last N
 * quarters of analyst-relevant calculated metrics so an analyst can see
 * direction-of-travel for revenue growth, EBITDA margin, PAT margin, and
 * segment margin without leaving the company page.
 *
 * Historical min / max / median bands are listed under the chart; anomalous
 * quarters render as larger amber dots on the line.
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
  const bands = useMemo(
    () => (data ?? []).filter((t) => t.band && (t.band.min != null || t.band.max != null)),
    [data],
  );

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
              Amber dots mark quarters flagged as historical anomalies.
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
                  dot={<AnomalyDot dataKey={trend.metric_code} />}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {bands.length > 0 && (
          <div className="mt-3 pt-3 border-t border-line/60 grid gap-1.5 sm:grid-cols-2">
            {bands.map((trend) => (
              <div
                key={trend.metric_code}
                className="text-[11px] text-ink-mute"
                title="Historical envelope from the last 16 non-quarantined quarters"
              >
                <span className="font-medium text-ink-soft">{trend.metric_name}</span>
                {" · "}
                {formatBandValue(trend.band?.min, trend.unit)} –{" "}
                {formatBandValue(trend.band?.max, trend.unit)}
                {trend.band?.median != null && (
                  <>
                    {" "}
                    (median {formatBandValue(trend.band.median, trend.unit)})
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
