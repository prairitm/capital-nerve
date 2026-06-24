import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronRight, Search } from "lucide-react";
import { api } from "@/api/client";
import type { Company } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { Empty } from "@/components/common/Empty";

export function Companies() {
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["companies", q],
    queryFn: () => api<Company[]>("/companies", { query: { search: q, limit: 200 } }),
  });

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-ink">Companies</h1>
        <p className="text-sm text-ink-mute mt-0.5">Every company in the pipeline DB.</p>
      </div>

      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by name or ticker…"
          className="input pl-9"
        />
      </div>

      {isLoading ? (
        <PageLoader />
      ) : !data || data.length === 0 ? (
        <Empty title="No companies" description="Ingest a filing through the v3 pipeline." />
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {data.map((c) => (
            <Link
              key={c.id}
              to={`/company/${c.ticker || c.id}`}
              className="group flex items-center justify-between gap-3 rounded-xl border border-line/60 bg-surface-2/40 px-4 py-3 hover:border-line-strong hover:bg-surface-2 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="size-9 rounded-lg bg-surface-3 grid place-items-center text-ink-mute shrink-0">
                  <Building2 size={18} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink truncate">{c.name}</div>
                  <div className="text-xs text-ink-soft">
                    {c.ticker}
                    {c.industry && <span className="text-ink-fade"> · {c.industry}</span>}
                  </div>
                </div>
              </div>
              <ChevronRight size={16} className="text-ink-soft shrink-0" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
