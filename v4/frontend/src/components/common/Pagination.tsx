import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationState<T> {
  page: number;
  pageCount: number;
  pageItems: T[];
  pageStart: number;
  pageEnd: number;
  setPage: (page: number) => void;
}

export function usePagination<T>(
  items: T[],
  pageSize = 10,
  resetKey?: string | number | boolean | null,
): PaginationState<T> {
  const [page, setPageState] = useState(1);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));

  useEffect(() => {
    setPageState(1);
  }, [resetKey, pageSize]);

  useEffect(() => {
    setPageState((current) => Math.min(current, pageCount));
  }, [pageCount]);

  const safePage = Math.min(page, pageCount);
  const pageStart = items.length === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const pageEnd = Math.min(safePage * pageSize, items.length);

  const pageItems = useMemo(
    () => items.slice((safePage - 1) * pageSize, safePage * pageSize),
    [items, pageSize, safePage],
  );

  const setPage = (nextPage: number) => {
    setPageState(Math.min(Math.max(nextPage, 1), pageCount));
  };

  return { page: safePage, pageCount, pageItems, pageStart, pageEnd, setPage };
}

export function Pagination({
  page,
  pageCount,
  pageStart,
  pageEnd,
  total,
  onPageChange,
}: {
  page: number;
  pageCount: number;
  pageStart: number;
  pageEnd: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  if (total === 0 || pageCount <= 1) return null;

  return (
    <div className="border-t border-line/60 px-5 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
      <span className="text-ink-mute num">
        {pageStart}-{pageEnd} of {total}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-xs disabled:opacity-40 disabled:pointer-events-none"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={14} />
        </button>
        <span className="text-ink-soft num">
          Page {page} of {pageCount}
        </span>
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-xs disabled:opacity-40 disabled:pointer-events-none"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pageCount}
          aria-label="Next page"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
