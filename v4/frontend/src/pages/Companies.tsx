import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "@/api/client";
import type { CompanyListItem, NseCompanySearchResult } from "@/api/types";
import { CompanyCard } from "@/components/company/CompanyCard";
import { NseCompanyResult } from "@/components/company/NseCompanyResult";
import { Empty } from "@/components/common/Empty";
import { ErrorState, PageHeader, PageSkeleton } from "@/components/common/DashboardUI";

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
    placeholderData: keepPreviousData,
  });
  const nseQuery = useQuery({
    queryKey: ["nse-companies", query],
    queryFn: () => api<NseCompanySearchResult[]>("/nse-companies/search", { query: { q: query, limit: 20 } }),
    enabled: query.trim().length >= 2,
    staleTime: 5 * 60 * 1000,
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
  const moreNseCompanies = useMemo(() => {
    const coveredSymbols = new Set((companyQuery.data ?? []).map((company) => company.ticker?.toUpperCase()).filter(Boolean));
    return (nseQuery.data ?? []).filter(
      (result) => result.coverage_status === "available" && !coveredSymbols.has(result.symbol.toUpperCase()),
    );
  }, [companyQuery.data, nseQuery.data]);
  const hasDirectoryQuery = query.trim().length >= 2;
  const showEmpty = companies.length === 0
    && (!hasDirectoryQuery || (!nseQuery.isLoading && moreNseCompanies.length === 0));

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

      {companies.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {companies.map((company) => <CompanyCard key={company.id} company={company} />)}
        </div>
      )}

      {hasDirectoryQuery && nseQuery.isLoading && (
        <p className="text-sm text-ink-mute">Searching the NSE directory…</p>
      )}

      {hasDirectoryQuery && nseQuery.isError && (
        <section className="card p-4 text-sm text-danger" role="alert">
          The NSE company directory could not be searched. Try again shortly.
        </section>
      )}

      {moreNseCompanies.length > 0 && (
        <section className="space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-ink">More companies on NSE</h2>
            <p className="mt-1 text-xs text-ink-mute">Start monitoring a company to add it to CapitalNerve coverage. New supported filings will be processed after it is added.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {moreNseCompanies.map((result) => <NseCompanyResult key={result.symbol} result={result} />)}
          </div>
        </section>
      )}

      {showEmpty && (
        <Empty title={query || industry ? "No matching companies" : "No companies available"} description={query || industry ? "Adjust the search or industry filter to broaden the results." : "Covered companies will appear after their first filing is processed."} action={(query || industry) && <button className="btn-secondary" onClick={() => { setSearch(""); setParams(new URLSearchParams()); }}>Clear filters</button>} />
      )}
    </div>
  );
}
