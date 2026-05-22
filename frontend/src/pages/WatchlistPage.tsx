import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "@/api/client";
import type { WatchItem, WatchlistResponse } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { Empty } from "@/components/common/Empty";

export function WatchlistPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api<WatchlistResponse>("/watchlist"),
  });

  const watchItemsQ = useQuery({
    queryKey: ["watchItems"],
    queryFn: () => api<WatchItem[]>("/watch-items"),
  });

  const remove = useMutation({
    mutationFn: async (company_id: number) => {
      await api(`/watchlist/companies/${company_id}`, { method: "DELETE" });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });

  const removeItem = useMutation({
    mutationFn: async (id: number) => {
      await api(`/watch-items/${id}`, { method: "DELETE" });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchItems"] }),
  });

  if (isLoading) return <PageLoader />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">My Watchlist</h1>
        <p className="text-sm text-ink-mute">
          What changed in companies you care about — and what you said you would monitor.
        </p>
      </div>

      <section>
        {data && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-4">
            <Stat label="Tracked" value={data.summary.tracked} />
            <Stat label="New Events" value={data.summary.new_events} />
            <Stat label="Negative" value={data.summary.negative_signals} tone="negative" />
            <Stat label="Positive" value={data.summary.positive_signals} tone="positive" />
            <Stat label="Red Flags" value={data.summary.red_flags} tone="negative" />
          </div>
        )}

        {!data || data.companies.length === 0 ? (
          <Empty
            title="Watchlist is empty"
            description="Open a company and click Add to watchlist to start tracking."
            action={
              <button onClick={() => navigate("/companies")} className="btn-primary">
                Browse companies
              </button>
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.companies.map((c) => {
              const symbol = c.company.nse_symbol || c.company.bse_code;
              const openCompany = () => {
                if (symbol) navigate(`/company/${symbol}`);
              };
              return (
                <article
                  key={c.company.company_id}
                  role="button"
                  tabIndex={0}
                  onClick={openCompany}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openCompany();
                    }
                  }}
                  className="group card p-4 cursor-pointer hover:border-line-strong hover:bg-surface-2/50 transition-colors text-left w-full"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold truncate text-ink group-hover:text-ink-mute">
                        {c.company.short_name || c.company.company_name}
                      </div>
                      <div className="text-[11px] text-ink-soft truncate">
                        {c.company.nse_symbol} · {c.company.sector_name}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        remove.mutate(c.company.company_id);
                      }}
                      className="btn-ghost p-2 shrink-0"
                      title="Remove from watchlist"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  {c.latest_card_headline && (
                    <>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        <SignalBadge direction={c.latest_signal} />
                        <SeverityBadge level={c.severity} />
                      </div>
                      <div className="mt-2 text-sm">{c.latest_card_headline}</div>
                      {c.watch_next && (
                        <p className="mt-1 text-xs text-ink-mute">Watch: {c.watch_next}</p>
                      )}
                    </>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      {watchItemsQ.data && watchItemsQ.data.length > 0 && (
        <section>
          <h2 className="text-base font-semibold mb-3">Watch Items</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {watchItemsQ.data.map((w) => (
              <div key={w.watch_item_id} className="card-2 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-[11px] text-ink-soft uppercase tracking-wider">
                      {w.company_name}
                      {w.company_symbol ? ` · ${w.company_symbol}` : ""}
                    </div>
                    <div className="font-medium mt-1">{w.title}</div>
                  </div>
                  <button
                    onClick={() => removeItem.mutate(w.watch_item_id)}
                    className="btn-ghost p-2"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                {w.description && (
                  <p className="text-xs text-ink-mute mt-1">{w.description}</p>
                )}
                {w.condition_operator && w.target_value !== null && (
                  <div className="mt-2 text-xs">
                    Alert if value {w.condition_operator} <span className="num">{w.target_value}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "negative" | "positive" }) {
  return (
    <div className="card p-3">
      <div className="text-[11px] text-ink-soft uppercase tracking-wider">{label}</div>
      <div
        className={
          "text-2xl font-semibold num " +
          (tone === "negative" ? "text-negative" : tone === "positive" ? "text-positive" : "")
        }
      >
        {value}
      </div>
    </div>
  );
}
