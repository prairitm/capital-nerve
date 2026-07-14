import { Heart, Loader2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "@/api/client";
import type { WatchlistMutationResponse } from "@/api/types";

export function WatchlistButton({ companyId, watched, compact = false }: { companyId: string; watched: boolean; compact?: boolean }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => api<WatchlistMutationResponse>(`/watchlist/companies/${companyId}`, { method: watched ? "DELETE" : "PUT" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
      void queryClient.invalidateQueries({ queryKey: ["company"] });
      void queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
  const label = watched ? "Remove from watchlist" : "Add to watchlist";
  return (
    <button
      type="button"
      className={clsx(compact ? "focus-ring grid size-9 place-items-center rounded-xl border" : "btn-secondary", watched ? "border-brand/35 bg-brand/10 text-brand-soft" : "border-line text-ink-mute")}
      aria-label={label}
      title={label}
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {mutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Heart size={compact ? 16 : 15} fill={watched ? "currentColor" : "none"} />}
      {!compact && (watched ? "Watching" : "Add to watchlist")}
    </button>
  );
}
