import type { Signal } from "@/api/types";
import { SignalTable } from "@/components/signals/SignalTable";

interface Props {
  signals: Signal[];
  title?: string;
}

/** Compact signal table for in-context pages (event detail, company hub). */
export function EventSignalList({
  signals,
  title = "Signals fired",
}: Props) {
  return <SignalTable signals={signals} title={title} />;
}
