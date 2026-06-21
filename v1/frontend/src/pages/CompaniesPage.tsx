import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "@/api/client";
import type { CompanyBrief } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { formatCr } from "@/lib/format";

export function CompaniesPage() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["companies", q],
    queryFn: () => api<CompanyBrief[]>("/v1/companies", { query: { search: q } }),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Companies</h1>
        <p className="text-sm text-ink-mute">Browse companies with recent intelligence.</p>
      </div>
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by company name or symbol…"
          className="input pl-9"
        />
      </div>
      {isLoading ? (
        <PageLoader />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data?.map((c) => (
            <Link
              to={`/company/${c.nse_symbol || c.bse_code}`}
              key={c.company_id}
              className="card p-4 hover:border-line-strong transition-colors block"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-semibold truncate">{c.company_name}</div>
                  <div className="text-xs text-ink-soft truncate">
                    {c.nse_symbol ? `NSE: ${c.nse_symbol}` : ""}
                    {c.bse_code ? ` · BSE: ${c.bse_code}` : ""}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs">
                <span className="text-ink-mute">{c.sector_name}</span>
                <span className="num text-ink">{formatCr(c.market_cap_cr)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
