import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { pdfjs } from "react-pdf";
import pdfjsWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { api, apiBlob } from "@/api/client";
import type { DocumentDetail, ExtractedValue, SourceLocateResult } from "@/api/types";
import { FactSourceLink } from "@/components/common/FactSourceLink";
import { PageLoader, Spinner } from "@/components/common/Spinner";
import {
  ContinuousPdfViewer,
  type ContinuousPdfViewerHandle,
} from "@/components/pdf/ContinuousPdfViewer";
import { PdfViewerToolbar } from "@/components/pdf/PdfViewerToolbar";
import { documentDisplayTitle, formatMetricValue } from "@/lib/format";
import { parseSourceBbox } from "@/lib/pdfHighlight";

pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorker;

function parsePageParam(raw: string | null): number | null {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.round(value) : null;
}

function summaryFactValue(fact: ExtractedValue): string {
  if (
    fact.value_lower != null &&
    fact.value_upper != null &&
    fact.value_lower !== fact.value_upper
  ) {
    return `${formatMetricValue(fact.value_lower, fact.unit)} – ${formatMetricValue(
      fact.value_upper,
      fact.unit,
    )}`;
  }
  if (fact.value_numeric != null) return formatMetricValue(fact.value_numeric, fact.unit);
  return fact.value_text?.trim() || "—";
}

export function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [searchParams] = useSearchParams();
  const pageFromUrl = parsePageParam(searchParams.get("page"));
  const highlightText = searchParams.get("highlight");
  const highlightValue = searchParams.get("value");
  const highlightContext = searchParams.get("context");
  const viewerHandleRef = useRef<ContinuousPdfViewerHandle>(null);
  const [viewerWidthElement, setViewerWidthElement] = useState<HTMLDivElement | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(pageFromUrl ?? 1);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(true);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [fitPageWidth, setFitPageWidth] = useState(760);
  const [zoom, setZoom] = useState(1);

  const locateQuery = useMemo(() => {
    const query: Record<string, string> = { text: highlightText! };
    if (pageFromUrl != null) query.page = String(pageFromUrl);
    if (highlightValue?.trim()) query.value = highlightValue.trim();
    if (highlightContext?.trim()) query.context = highlightContext.trim();
    return query;
  }, [highlightText, highlightValue, highlightContext, pageFromUrl]);

  const { data: locate, isLoading: locating } = useQuery({
    queryKey: [
      "document-locate",
      documentId,
      highlightText,
      highlightValue,
      highlightContext,
      pageFromUrl,
    ],
    queryFn: () =>
      api<SourceLocateResult>(`/documents/${documentId}/locate`, {
        query: locateQuery,
      }),
    enabled: !!documentId && !!highlightText?.trim(),
  });

  const targetPage = pageFromUrl ?? locate?.page ?? null;
  const sourceBbox = useMemo(() => parseSourceBbox(locate?.bbox), [locate?.bbox]);
  const highlightKey = useMemo(
    () =>
      highlightText?.trim()
        ? [documentId, targetPage, highlightText, highlightValue].join(":")
        : null,
    [documentId, highlightText, highlightValue, targetPage],
  );

  useEffect(() => {
    if (targetPage != null) setCurrentPage(targetPage);
  }, [targetPage]);

  useEffect(() => {
    const element = viewerWidthElement;
    if (!element) return;
    const update = () => {
      const availableWidth = Math.max(240, element.clientWidth - 64);
      setFitPageWidth(Math.min(1040, availableWidth));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [viewerWidthElement]);

  useEffect(() => {
    if (!documentId) return;
    const controller = new AbortController();
    setPdfLoading(true);
    setPdfError(null);
    apiBlob(`/documents/${documentId}/file`, { signal: controller.signal })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        setPdfUrl((previousUrl) => {
          if (previousUrl) URL.revokeObjectURL(previousUrl);
          return url;
        });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setPdfError(error instanceof Error ? error.message : "Failed to load PDF");
      })
      .finally(() => {
        if (!controller.signal.aborted) setPdfLoading(false);
      });
    return () => {
      controller.abort();
      setPdfUrl((previousUrl) => {
        if (previousUrl) URL.revokeObjectURL(previousUrl);
        return null;
      });
    };
  }, [documentId]);

  const { data, isLoading } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api<DocumentDetail>(`/documents/${documentId}`),
    enabled: !!documentId,
  });

  const handlePageChange = useCallback(
    (pageNumber: number) => {
      const nextPage = Math.min(Math.max(pageNumber, 1), Math.max(1, numPages));
      setCurrentPage(nextPage);
      viewerHandleRef.current?.scrollToPage(nextPage);
    },
    [numPages],
  );

  const handleZoomChange = useCallback((nextZoom: number) => {
    setZoom(nextZoom);
    requestAnimationFrame(() => viewerHandleRef.current?.scrollToPage(currentPage, "auto"));
  }, [currentPage]);
  const ignoreHighlightStatus = useCallback(() => {}, []);

  if (isLoading || (highlightText?.trim() && locating)) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Document not found.</div>;

  const { document: documentInfo, company, event } = data;
  const title = documentDisplayTitle(documentInfo, event);
  const showFilingSummary = Boolean(data.filing_summary?.highlights.length);
  const showSidePanel = showFilingSummary;
  const hasEvidence = Boolean(highlightText?.trim() && targetPage != null);
  const pageWidth = Math.max(240, Math.round(fitPageWidth * zoom));

  return (
    <div className="mx-auto flex h-[calc(100dvh-9rem)] min-h-[30rem] max-w-[1500px] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card lg:h-[calc(100dvh-3.5rem)] lg:min-h-[34rem]">
      <PdfViewerToolbar
        title={title}
        companyName={company?.name}
        currentPage={currentPage}
        numPages={numPages}
        zoom={zoom}
        pdfUrl={pdfUrl}
        hasEvidence={hasEvidence}
        onPageChange={handlePageChange}
        onZoomChange={handleZoomChange}
        onFitWidth={() => handleZoomChange(1)}
        onReturnToEvidence={() => viewerHandleRef.current?.scrollToEvidence()}
      />

      <div
        className={`grid min-h-0 flex-1 ${
          showSidePanel
            ? "grid-rows-[minmax(0,1fr)_minmax(10rem,40%)] lg:grid-cols-[minmax(0,1fr)_22rem] lg:grid-rows-1"
            : "grid-cols-1"
        }`}
      >
        <div ref={setViewerWidthElement} className="min-h-0 min-w-0">
          {pdfLoading ? (
            <div className="grid h-full place-items-center">
              <Spinner size={22} />
            </div>
          ) : pdfError ? (
            <div className="grid h-full place-items-center px-5 text-sm text-negative">
              {pdfError}
            </div>
          ) : pdfUrl ? (
            <ContinuousPdfViewer
              ref={viewerHandleRef}
              file={pdfUrl}
              pageWidth={pageWidth}
              targetPage={targetPage}
              highlightKey={highlightKey}
              highlightText={highlightText}
              highlightValue={highlightValue}
              referenceText={locate?.reference_text ?? null}
              bbox={sourceBbox}
              onDocumentLoad={(loadedPages) => {
                setNumPages(loadedPages);
                setCurrentPage((page) => Math.min(Math.max(page, 1), loadedPages));
              }}
              onCurrentPageChange={setCurrentPage}
              onHighlightStatus={ignoreHighlightStatus}
            />
          ) : null}
        </div>

        {showSidePanel && (
          <aside className="min-h-0 overflow-y-auto border-t border-line bg-bg-soft/95 p-4 lg:border-l lg:border-t-0">
            {showFilingSummary && data.filing_summary && (
              <section>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-soft">
                  Filing summary
                </div>
                <p className="mb-3 text-[11px] leading-relaxed text-ink-soft">
                  Key facts selected from {data.filing_summary.available_fact_count} extracted
                  {data.filing_summary.available_fact_count === 1 ? " fact" : " facts"}. The full
                  fact set remains available on the event page.
                </p>
                <ul className="space-y-2.5">
                  {data.filing_summary.highlights.map((fact) => (
                    <li
                      key={`${fact.value_code}-${fact.segment ?? fact.scope_name ?? "company"}`}
                      className="rounded-xl border border-line/70 bg-surface-2/55 p-3"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[11px] text-ink-mute">{fact.value_name}</div>
                          <div className="mt-0.5 break-words text-sm font-medium leading-snug text-ink">
                            {summaryFactValue(fact)}
                          </div>
                        </div>
                        <FactSourceLink documentId={documentId ?? null} fact={fact} />
                      </div>
                      {fact.source_page != null && (
                        <div className="mt-2 text-[10px] text-ink-soft">Source: p.{fact.source_page}</div>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
