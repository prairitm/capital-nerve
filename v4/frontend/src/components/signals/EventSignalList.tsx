import type { MetricValue, Signal } from "@/api/types";
import { SignalTable } from "@/components/signals/SignalTable";

interface Props {
  signals: Signal[];
  metrics?: MetricValue[];
  title?: string;
}

/** Compact signal table for in-context pages (event detail, company hub). */
export function EventSignalList({
  signals,
  metrics = [],
  title = "Signals fired",
}: Props) {
  return <SignalTable signals={signals} metrics={metrics} title={title} />;
}
