import { useQuery } from "@tanstack/react-query";
import { Heart } from "lucide-react";
import { api } from "@/api/client";
import type { WatchlistResponse } from "@/api/types";
import { CompanyCard } from "@/components/company/CompanyCard";
import { Empty } from "@/components/common/Empty";
import { ErrorState, PageHeader, PageSkeleton } from "@/components/common/DashboardUI";

export function Watchlist() {
  const query = useQuery({ queryKey: ["watchlist"], queryFn: () => api<WatchlistResponse>("/watchlist") });
  if (query.isLoading) return <PageSkeleton rows={4} />;
  if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;
  const companies = query.data?.companies ?? [];
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader eyebrow="Personal coverage" title="My watchlist" description="Companies you are actively monitoring, ordered by when they were added." action={<span className="chip-neutral"><Heart size={12} fill="currentColor" />{companies.length} tracked</span>} />
      {companies.length === 0 ? <Empty title="Your watchlist is empty" description="Search the company universe and use the heart control to start monitoring companies." /> : <div className="grid gap-3 md:grid-cols-2">{companies.map((company) => <CompanyCard key={company.id} company={company} />)}</div>}
    </div>
  );
}
