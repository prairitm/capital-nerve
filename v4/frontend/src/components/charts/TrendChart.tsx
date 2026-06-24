import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendSeries } from "@/api/types";
import { formatPeriodLabel } from "@/lib/format";

/** Compact multi-quarter line chart for one metric. Forked conceptually from
 * v1's SignalTrendChart but driven by the native TrendSeries shape. */
export function TrendChart({ series }: { series: TrendSeries }) {
  const data = series.points
    .filter((p) => p.value != null)
    .map((p) => ({
      label: formatPeriodLabel(p.period_end),
      value: p.value,
    }));

  if (data.length === 0) {
    return <div className="text-xs text-ink-soft py-6 text-center">No trend data yet.</div>;
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-ink">{series.metric_name}</span>
        <span className="text-xs text-ink-soft">{series.unit}</span>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top: 6, right: 6, bottom: 4, left: -18 }}>
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "#6B7488" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#6B7488" }}
            axisLine={false}
            tickLine={false}
            width={42}
          />
          <Tooltip
            contentStyle={{
              background: "#141A26",
              border: "1px solid #222B3D",
              borderRadius: 12,
              fontSize: 12,
              color: "#E6EAF2",
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#60A5FA"
            strokeWidth={2}
            dot={{ r: 3, fill: "#60A5FA" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
