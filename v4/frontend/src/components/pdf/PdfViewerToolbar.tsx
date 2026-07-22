import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  LocateFixed,
  Maximize2,
  Minus,
  Plus,
} from "lucide-react";
import { BackButton } from "@/components/common/BackButton";

type PdfViewerToolbarProps = {
  title: string;
  companyName?: string | null;
  currentPage: number;
  numPages: number;
  zoom: number;
  pdfUrl: string | null;
  hasEvidence: boolean;
  onPageChange: (page: number) => void;
  onZoomChange: (zoom: number) => void;
  onFitWidth: () => void;
  onReturnToEvidence: () => void;
};

function clampPage(page: number, numPages: number): number {
  if (!Number.isFinite(page)) return 1;
  return Math.min(Math.max(Math.round(page), 1), Math.max(1, numPages));
}

export function PdfViewerToolbar({
  title,
  companyName,
  currentPage,
  numPages,
  zoom,
  pdfUrl,
  hasEvidence,
  onPageChange,
  onZoomChange,
  onFitWidth,
  onReturnToEvidence,
}: PdfViewerToolbarProps) {
  const [pageInput, setPageInput] = useState(String(currentPage));

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  const commitPage = () => {
    const nextPage = clampPage(Number(pageInput), numPages);
    setPageInput(String(nextPage));
    onPageChange(nextPage);
  };

  return (
    <header className="relative z-20 flex min-h-16 flex-wrap items-center gap-3 border-b border-line/80 bg-surface/95 px-3 py-2.5 backdrop-blur md:flex-nowrap md:px-4">
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <BackButton fallback="/companies" />
        <div className="hidden h-7 w-px bg-line/80 sm:block" />
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold text-ink" title={title}>
            {title}
          </h1>
          {companyName && (
            <p className="truncate text-[11px] text-ink-soft">{companyName}</p>
          )}
        </div>
      </div>

      <div className="order-3 flex w-full items-center justify-between gap-2 md:order-none md:w-auto md:justify-start">
        <div className="flex items-center rounded-xl border border-line bg-bg-deep/55 p-1">
          <button
            type="button"
            className="focus-ring grid size-8 place-items-center rounded-lg text-ink-mute transition-colors hover:bg-surface-2 hover:text-ink disabled:pointer-events-none disabled:opacity-35"
            aria-label="Previous page"
            title="Previous page"
            disabled={currentPage <= 1}
            onClick={() => onPageChange(currentPage - 1)}
          >
            <ChevronLeft size={15} />
          </button>
          <label className="flex items-center gap-1.5 px-1 text-xs text-ink-soft">
            <span className="sr-only">Page number</span>
            <input
              className="num h-7 w-10 rounded-md border border-line/80 bg-surface px-1 text-center text-xs text-ink outline-none focus:border-brand/70 focus:ring-2 focus:ring-brand/15"
              aria-label="Page number"
              inputMode="numeric"
              value={pageInput}
              onChange={(event) => setPageInput(event.target.value.replace(/[^0-9]/g, ""))}
              onBlur={commitPage}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.currentTarget.blur();
                }
              }}
            />
            <span className="num whitespace-nowrap">of {numPages || "—"}</span>
          </label>
          <button
            type="button"
            className="focus-ring grid size-8 place-items-center rounded-lg text-ink-mute transition-colors hover:bg-surface-2 hover:text-ink disabled:pointer-events-none disabled:opacity-35"
            aria-label="Next page"
            title="Next page"
            disabled={numPages === 0 || currentPage >= numPages}
            onClick={() => onPageChange(currentPage + 1)}
          >
            <ChevronRight size={15} />
          </button>
        </div>

        <div className="flex items-center rounded-xl border border-line bg-bg-deep/55 p-1">
          <button
            type="button"
            className="focus-ring grid size-8 place-items-center rounded-lg text-ink-mute transition-colors hover:bg-surface-2 hover:text-ink disabled:pointer-events-none disabled:opacity-35"
            aria-label="Zoom out"
            title="Zoom out"
            disabled={zoom <= 0.75}
            onClick={() => onZoomChange(Math.max(0.75, zoom - 0.1))}
          >
            <Minus size={14} />
          </button>
          <span className="num w-11 text-center text-[11px] text-ink-soft">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            className="focus-ring grid size-8 place-items-center rounded-lg text-ink-mute transition-colors hover:bg-surface-2 hover:text-ink disabled:pointer-events-none disabled:opacity-35"
            aria-label="Zoom in"
            title="Zoom in"
            disabled={zoom >= 2}
            onClick={() => onZoomChange(Math.min(2, zoom + 0.1))}
          >
            <Plus size={14} />
          </button>
          <button
            type="button"
            className="focus-ring grid size-8 place-items-center rounded-lg text-ink-mute transition-colors hover:bg-surface-2 hover:text-ink"
            aria-label="Fit to width"
            title="Fit to width"
            onClick={onFitWidth}
          >
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {hasEvidence && (
          <button
            type="button"
            className="focus-ring hidden h-9 items-center gap-1.5 rounded-xl border border-positive/25 bg-positive-bg px-2.5 text-xs font-medium text-positive transition-colors hover:border-positive/45 sm:inline-flex"
            onClick={onReturnToEvidence}
          >
            <LocateFixed size={14} />
            Evidence
          </button>
        )}
        {pdfUrl && (
          <>
            <a
              className="focus-ring grid size-9 place-items-center rounded-xl text-ink-mute transition-colors hover:bg-surface-2 hover:text-ink"
              href={pdfUrl}
              target="_blank"
              rel="noreferrer"
              aria-label="Open PDF in new tab"
              title="Open PDF in new tab"
            >
              <ExternalLink size={16} />
            </a>
            <a
              className="focus-ring grid size-9 place-items-center rounded-xl text-ink-mute transition-colors hover:bg-surface-2 hover:text-ink"
              href={pdfUrl}
              download
              aria-label="Download PDF"
              title="Download PDF"
            >
              <Download size={16} />
            </a>
          </>
        )}
      </div>
    </header>
  );
}
