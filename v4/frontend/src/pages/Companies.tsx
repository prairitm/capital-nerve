import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowUpRight, CalendarDays, Search } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type { CompanyListItem, SeverityLevel } from "@/api/types";
import { Empty } from "@/components/common/Empty";
import { ErrorState, PageHeader, PageSkeleton } from "@/components/common/DashboardUI";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { formatDate } from "@/lib/format";

const severityRank: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };

export function Companies() {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const industry = params.get("industry") ?? "";
  const sort = params.get("sort") ?? "activity";
  const [search, setSearch] = useState(query);

  useEffect(() => setSearch(query), [query]);
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      const next = new URLSearchParams(params);
      if (search.trim()) next.set("q", search.trim()); else next.delete("q");
      setParams(next, { replace: true });
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [search]); // URL params intentionally update only after the debounce

  const companyQuery = useQuery({
    queryKey: ["companies", query],
    queryFn: () => api<CompanyListItem[]>("/companies", { query: { search: query, limit: 200 } }),
  });

  const industries = useMemo(() => [...new Set((companyQuery.data ?? []).map((c) => c.industry).filter(Boolean) as string[])].sort(), [companyQuery.data]);
  const companies = useMemo(() => {
    const rows = (companyQuery.data ?? []).filter((c) => !industry || c.industry === industry);
    return [...rows].sort((a, b) => {
      if (sort === "name") return (a.name ?? "").localeCompare(b.name ?? "");
      if (sort === "signals") return b.signal_count - a.signal_count || (a.name ?? "").localeCompare(b.name ?? "");
      if (sort === "severity") return (severityRank[b.highest_severity ?? ""] ?? 0) - (severityRank[a.highest_severity ?? ""] ?? 0);
      return (b.latest_event_date ?? "").localeCompare(a.latest_event_date ?? "");
    });
  }, [companyQuery.data, industry, sort]);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  };

  if (companyQuery.isLoading) return <PageSkeleton rows={4} />;
  if (companyQuery.isError) return <ErrorState onRetry={() => void companyQuery.refetch()} />;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <PageHeader eyebrow="Coverage universe" title="Companies" description="Financial performance, reporting activity, and material signals across covered companies." action={<span className="chip-neutral">{companies.length} covered</span>} />

      <section className="card p-3 md:p-4">
        <div className="grid gap-3 md:grid-cols-[minmax(15rem,1fr)_12rem_10rem]">
          <label className="relative min-w-0">
            <span className="sr-only">Search companies</span>
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search company or ticker" className="input pl-9" />
          </label>
          <label><span className="sr-only">Industry</span><select value={industry} onChange={(e) => setParam("industry", e.target.value)} className="input"><option value="">All industries</option>{industries.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label><span className="sr-only">Sort companies</span><select value={sort} onChange={(e) => setParam("sort", e.target.value)} className="input"><option value="activity">Latest activity</option><option value="severity">Materiality</option><option value="signals">Signal count</option><option value="name">Company name</option></select></label>
        </div>
      </section>

      {companies.length === 0 ? (
        <Empty title={query || industry ? "No matching companies" : "No companies available"} description={query || industry ? "Adjust the search or industry filter to broaden the results." : "Covered companies will appear after their first filing is processed."} action={(query || industry) && <button className="btn-secondary" onClick={() => { setSearch(""); setParams(new URLSearchParams()); }}>Clear filters</button>} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {companies.map((company) => <CompanyCard key={company.id} company={company} />)}
        </div>
      )}
    </div>
  );
}

function CompanyCard({ company }: { company: CompanyListItem }) {
  const ticker = company.ticker ?? company.id;
  const initials = (company.ticker || company.name || "CN").slice(0, 3).toUpperCase();
  return (
    <Link to={`/company/${ticker}`} className="focus-ring group card flex min-w-0 items-start gap-4 p-4 transition-colors hover:border-line-strong hover:bg-surface-2/55">
      <div className="grid size-11 shrink-0 place-items-center rounded-xl border border-brand/20 bg-brand/10 text-xs font-bold tracking-wide text-brand-soft">{initials}</div>
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="min-w-0"><h2 className="truncate text-sm font-semibold text-ink">{company.name}</h2><p className="mt-0.5 truncate text-xs text-ink-mute">{company.ticker}{company.industry ? ` · ${company.industry}` : ""}</p></div>
          <ArrowUpRight size={16} className="shrink-0 text-ink-soft transition-colors group-hover:text-brand-soft" />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-mute">
          <span className="inline-flex items-center gap-1.5"><CalendarDays size={13} />{company.latest_period_label ?? formatDate(company.latest_event_date)}</span>
          <span className="inline-flex items-center gap-1.5"><Activity size={13} />{company.signal_count} {company.signal_count === 1 ? "signal" : "signals"}</span>
          {company.highest_severity && <SeverityBadge level={company.highest_severity as SeverityLevel} />}
        </div>
      </div>
    </Link>
  );
}
