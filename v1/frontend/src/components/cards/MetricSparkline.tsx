import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import type { FinancialTrend } from "@/api/types";
import { formatMetricAmount, formatPct } from "@/lib/format";

export function MetricSparkline({ trend }: { trend: FinancialTrend }) {
  const data = trend.points.map((p) => ({ ...p, value: p.value ?? 0 }));
  const last = data[data.length - 1]?.value;

  return (
    <div className="rounded-lg bg-surface-2 border border-line/60 p-3 min-w-0">
      <div className="text-[11px] uppercase tracking-wider text-ink-soft truncate">
        {trend.metric_name}
      </div>
      <div className="text-sm font-semibold num mt-0.5">
        {last == null
          ? "—"
          : trend.unit === "%"
            ? formatPct(last, 1)
            : formatMetricAmount(last, trend.unit ?? "")}
        {trend.unit && trend.unit !== "%" && (
          <span className="text-ink-soft text-xs font-normal ml-0.5">{trend.unit}</span>
        )}
      </div>
      <div className="h-14 mt-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <Tooltip
              contentStyle={{
                background: "#141A26",
                border: "1px solid #222B3D",
                borderRadius: 8,
                fontSize: 11,
              }}
              formatter={(v: number) =>
                trend.unit === "%"
                  ? `${v.toFixed(1)}%`
                  : trend.unit === "Cr"
                    ? v.toLocaleString("en-IN", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })
                    : v.toLocaleString("en-IN")
              }
              labelFormatter={(_, payload) =>
                payload?.[0]?.payload?.period_label ?? ""
              }
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#3B82F6"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3, fill: "#60A5FA" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
