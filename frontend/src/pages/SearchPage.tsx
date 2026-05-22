import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "@/api/client";
import type { SearchResult } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") || "";
  const [q, setQ] = useState(initial);

  useEffect(() => {
    setQ(params.get("q") || "");
  }, [params]);

  const { data, isLoading } = useQuery({
    queryKey: ["search", q],
    queryFn: () => api<SearchResult>("/search", { query: { q } }),
    enabled: q.length > 0,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Search & Ask</h1>
        <p className="text-sm text-ink-mute">Search returns companies, events, and cards — not just documents.</p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setParams({ q });
        }}
        className="relative"
      >
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder='Try: "companies with revenue growth but margin compression"'
          className="input pl-9"
        />
      </form>

      {q.length === 0 ? (
        <div className="card p-6 text-sm text-ink-mute">
          Examples:
          <ul className="mt-2 space-y-1 list-disc list-inside">
            <li>Route Mobile</li>
            <li>Margin compression</li>
            <li>Profit quality</li>
            <li>Concall</li>
          </ul>
        </div>
      ) : isLoading || !data ? (
        <PageLoader />
      ) : (
        <div className="space-y-6">
          {data.companies.length > 0 && (
            <Section title="Companies">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.companies.map((c) => (
                  <Link
                    key={c.company_id}
                    to={`/company/${c.nse_symbol || c.bse_code}`}
                    className="card p-4 hover:border-line-strong block"
                  >
                    <div className="font-semibold">{c.company_name}</div>
                    <div className="text-xs text-ink-soft">
                      {c.nse_symbol} · {c.sector_name}
                    </div>
                  </Link>
                ))}
              </div>
            </Section>
          )}
          {data.cards.length > 0 && (
            <Section title="Intelligence Cards">
              <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3">
                {data.cards.map((c) => (
                  <div id={`card-${c.card_id}`} key={c.card_id} className="card rounded-xl p-3">
                    <div className="text-[10px] uppercase tracking-wider text-ink-soft">
                      {c.card_type.replace(/_/g, " ")}
                    </div>
                    <div className="text-sm font-medium mt-0.5 line-clamp-2">{c.headline}</div>
                    <p className="text-xs text-ink-mute mt-1 line-clamp-2">{c.one_line_summary}</p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <SignalBadge direction={c.signal_direction} />
                      <SeverityBadge level={c.severity} />
                      <span className="text-[11px] text-ink-soft ml-auto">
                        {c.company_name}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}
          {data.events.length > 0 && (
            <Section title="Events">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {data.events.map((e) => (
                  <Link
                    key={e.event_id}
                    to={`/company/${e.company_symbol}/event/${e.event_id}`}
                    className="card p-4 hover:border-line-strong block"
                  >
                    <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                      {e.event_type.replace(/_/g, " ")}
                    </div>
                    <div className="font-medium mt-1">{e.event_title}</div>
                    <div className="text-xs text-ink-soft mt-1">
                      {e.company_name} · {new Date(e.event_date).toLocaleDateString()}
                    </div>
                  </Link>
                ))}
              </div>
            </Section>
          )}
          {data.companies.length === 0 && data.cards.length === 0 && data.events.length === 0 && (
            <div className="card p-6 text-sm text-ink-mute text-center">No matches.</div>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold mb-3">{title}</h2>
      {children}
    </section>
  );
}
