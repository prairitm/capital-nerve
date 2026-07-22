import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { pdfjs } from "react-pdf";
import pdfjsWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { FileSearch } from "lucide-react";
import { api, apiBlob } from "@/api/client";
import type { DocumentDetail, SourceLocateResult } from "@/api/types";
import { PageLoader, Spinner } from "@/components/common/Spinner";
import {
  ContinuousPdfViewer,
  type ContinuousPdfViewerHandle,
} from "@/components/pdf/ContinuousPdfViewer";
import { PdfViewerToolbar } from "@/components/pdf/PdfViewerToolbar";
import { documentDisplayTitle } from "@/lib/format";
import {
  buildEvidenceHighlights,
  highlightMatchInText,
  parseSourceBbox,
} from "@/lib/pdfHighlight";

pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorker;

function parsePageParam(raw: string | null): number | null {
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? Math.round(value) : null;
}

export function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [searchParams] = useSearchParams();
  const pageFromUrl = parsePageParam(searchParams.get("page"));
  const highlightText = searchParams.get("highlight");
  const highlightValue = searchParams.get("value");
  const highlightContext = searchParams.get("context");
  const viewerHandleRef = useRef<ContinuousPdfViewerHandle>(null);
  const viewerWidthRef = useRef<HTMLDivElement>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(pageFromUrl ?? 1);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(true);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [fitPageWidth, setFitPageWidth] = useState(760);
  const [zoom, setZoom] = useState(1);
  const [pdfHighlightMatched, setPdfHighlightMatched] = useState(false);
  const [highlightChecked, setHighlightChecked] = useState(false);

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
  const highlights = useMemo(
    () =>
      highlightText
        ? buildEvidenceHighlights([highlightText], highlightValue)
        : { patterns: [], quoteTexts: [], targetValues: [] },
    [highlightText, highlightValue],
  );
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
    setPdfHighlightMatched(false);
    setHighlightChecked(false);
  }, [highlightKey, locate?.bbox]);

  useEffect(() => {
    const element = viewerWidthRef.current;
    if (!element) return;
    const update = () => {
      const availableWidth = Math.max(240, element.clientWidth - 64);
      setFitPageWidth(Math.min(1040, availableWidth));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [pdfUrl, highlightChecked, pdfHighlightMatched]);

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

  if (isLoading || (highlightText?.trim() && locating)) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Document not found.</div>;

  const { document: documentInfo, company, event } = data;
  const title = documentDisplayTitle(documentInfo, event);
  const showMarkdownFallback = Boolean(
    highlightText?.trim() &&
      locate?.reference_text &&
      highlightChecked &&
      !pdfHighlightMatched &&
      sourceBbox == null,
  );
  const hasEvidence = Boolean(highlightText?.trim() && targetPage != null);
  const pageWidth = Math.max(240, Math.round(fitPageWidth * zoom));

  return (
    <div className="mx-auto flex h-[calc(100dvh-7.25rem)] min-h-[34rem] max-w-[1500px] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card lg:h-[calc(100dvh-3.5rem)]">
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
          showMarkdownFallback
            ? "grid-rows-[minmax(0,1fr)_minmax(10rem,auto)] lg:grid-cols-[minmax(0,1fr)_20rem] lg:grid-rows-1"
            : "grid-cols-1"
        }`}
      >
        <div ref={viewerWidthRef} className="min-h-0 min-w-0">
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
              onHighlightStatus={(matched) => {
                setPdfHighlightMatched(matched);
                setHighlightChecked(true);
              }}
            />
          ) : null}
        </div>

        {showMarkdownFallback && locate?.reference_text && (
          <aside className="min-h-0 overflow-y-auto border-t border-line bg-bg-soft/95 p-4 lg:border-l lg:border-t-0">
            <div className="mb-3 flex items-center gap-2 text-positive">
              <FileSearch size={15} />
              <h2 className="text-xs font-semibold uppercase tracking-[0.12em]">
                Parsed evidence
              </h2>
            </div>
            <p className="mb-3 text-[11px] leading-relaxed text-ink-soft">
              The PDF text layer could not be matched reliably. This is the parsed filing excerpt used by the extraction pipeline.
            </p>
            <div
              className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink"
              dangerouslySetInnerHTML={{
                __html: highlightMatchInText(locate.reference_text, highlights.patterns),
              }}
            />
          </aside>
        )}
      </div>
    </div>
  );
}
