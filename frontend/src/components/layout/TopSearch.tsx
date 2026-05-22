import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { SearchResult } from "@/api/types";

export function TopSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        (document.querySelector<HTMLInputElement>("#cn-top-search"))?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const { data } = useQuery({
    queryKey: ["topSearch", q],
    queryFn: () => api<SearchResult>("/search", { query: { q } }),
    enabled: q.length >= 2,
  });

  return (
    <div ref={ref} className="relative w-full">
      <div className="relative">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft pointer-events-none"
        />
        <input
          id="cn-top-search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && q.length > 0) {
              navigate(`/search?q=${encodeURIComponent(q)}`);
              setOpen(false);
            }
          }}
          placeholder="Search companies, signals…"
          className="input pl-9 text-base sm:text-sm"
        />
      </div>
      {open && q.length >= 2 && data && (
        <div className="absolute top-full left-0 right-0 mt-2 card p-2 max-h-[60vh] overflow-y-auto z-40">
          {data.companies.length === 0 &&
            data.events.length === 0 &&
            data.cards.length === 0 && (
              <div className="p-4 text-sm text-ink-mute">No matches.</div>
            )}
          {data.companies.length > 0 && (
            <Section title="Companies">
              {data.companies.slice(0, 4).map((c) => (
                <button
                  key={c.company_id}
                  onClick={() => {
                    navigate(`/company/${c.nse_symbol || c.bse_code}`);
                    setOpen(false);
                  }}
                  className="block w-full text-left px-3 py-2 rounded-lg hover:bg-surface-2"
                >
                  <div className="text-sm font-medium">{c.company_name}</div>
                  <div className="text-xs text-ink-soft">
                    {c.nse_symbol ? `NSE: ${c.nse_symbol}` : ""} {c.sector_name ? `· ${c.sector_name}` : ""}
                  </div>
                </button>
              ))}
            </Section>
          )}
          {data.cards.length > 0 && (
            <Section title="Intelligence Cards">
              {data.cards.slice(0, 4).map((c) => (
                <button
                  key={c.card_id}
                  onClick={() => {
                    navigate(`/search?q=${encodeURIComponent(q)}#card-${c.card_id}`);
                    setOpen(false);
                  }}
                  className="block w-full text-left px-3 py-2 rounded-lg hover:bg-surface-2"
                >
                  <div className="text-sm">{c.headline}</div>
                  <div className="text-xs text-ink-soft">{c.company_name}</div>
                </button>
              ))}
            </Section>
          )}
          {data.events.length > 0 && (
            <Section title="Events">
              {data.events.slice(0, 4).map((e) => (
                <button
                  key={e.event_id}
                  onClick={() => {
                    if (e.company_symbol) navigate(`/company/${e.company_symbol}/event/${e.event_id}`);
                    setOpen(false);
                  }}
                  className="block w-full text-left px-3 py-2 rounded-lg hover:bg-surface-2"
                >
                  <div className="text-sm">{e.event_title}</div>
                  <div className="text-xs text-ink-soft">
                    {e.company_name} · {new Date(e.event_date).toLocaleDateString()}
                  </div>
                </button>
              ))}
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="py-1.5">
      <div className="px-3 py-1 text-[11px] uppercase tracking-wider text-ink-soft">{title}</div>
      <div>{children}</div>
    </div>
  );
}
