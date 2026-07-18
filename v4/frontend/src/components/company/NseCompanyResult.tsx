import { Heart, Loader2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { NseCompanySearchResult, WatchlistMutationResponse } from "@/api/types";

export function NseCompanyResult({ result }: { result: NseCompanySearchResult }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      api<WatchlistMutationResponse>(
        `/watchlist/companies/by-symbol/${encodeURIComponent(result.symbol)}`,
        { method: "PUT" },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
      void queryClient.invalidateQueries({ queryKey: ["nse-companies"] });
      void queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  return (
    <article className="card flex min-w-0 items-center gap-3 p-4">
      <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-surface-2 text-[11px] font-bold tracking-wide text-ink-soft">
        {result.symbol.slice(0, 3)}
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-semibold text-ink">{result.name}</h3>
        <p className="mt-0.5 truncate text-xs text-ink-mute">
          {result.symbol}{result.series ? ` · ${result.series}` : ""}{result.isin ? ` · ${result.isin}` : ""}
        </p>
        {mutation.isError && (
          <p className="mt-1 text-xs text-danger" role="alert">{mutation.error.message}</p>
        )}
      </div>
      <button
        type="button"
        className="btn-secondary shrink-0"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Heart size={15} />}
        {mutation.isPending ? "Starting…" : "Start monitoring"}
      </button>
    </article>
  );
}
