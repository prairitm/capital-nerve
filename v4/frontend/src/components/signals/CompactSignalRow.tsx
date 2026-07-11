import { useNavigate } from "react-router-dom";
import type { Signal } from "@/api/types";
import { SignalBadge } from "@/components/common/SignalBadge";

interface Props {
  signal: Signal;
}

export function CompactSignalRow({ signal }: Props) {
  const navigate = useNavigate();
  const name = signal.signal_name || signal.title || signal.signal_type;

  return (
    <button
      type="button"
      onClick={() => navigate(`/signals/${signal.id}`)}
      className="w-full flex items-center gap-3 px-5 py-2 text-left hover:bg-surface-2/40 transition-colors group"
    >
      <span className="flex-1 min-w-0 text-sm font-medium text-ink leading-snug truncate">
        {name}
      </span>
      <SignalBadge direction={signal.direction} />
    </button>
  );
}
