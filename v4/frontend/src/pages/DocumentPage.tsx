import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Document, Page, pdfjs } from "react-pdf";
import pdfjsWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api, apiBlob } from "@/api/client";
import type { DocumentDetail, SourceLocateResult } from "@/api/types";
import { PageLoader, Spinner } from "@/components/common/Spinner";
import { BackButton } from "@/components/common/BackButton";
import { documentDisplayTitle } from "@/lib/format";
import {
  buildEvidenceHighlights,
  applyPdfPageHighlights,
  highlightMatchInText,
  parseSourceBbox,
  type SourceBbox,
} from "@/lib/pdfHighlight";

pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorker;

function parsePageParam(raw: string | null): number | null {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function PdfPageWithHighlights({
  pageNumber,
  pageWidth,
  highlightText,
  referenceText,
  bbox,
  onHighlightStatus,
}: {
  pageNumber: number;
  pageWidth: number;
  highlightText: string | null;
  referenceText: string | null;
  bbox: SourceBbox | null;
  onHighlightStatus?: (matched: boolean) => void;
}) {
  const pageWrapRef = useRef<HTMLDivElement>(null);
  const [pdfPageWidth, setPdfPageWidth] = useState(0);
  const highlights = useMemo(
    () => (highlightText ? buildEvidenceHighlights([highlightText]) : { patterns: [], quoteTexts: [] }),
    [highlightText],
  );
  const scale = pdfPageWidth > 0 ? pageWidth / pdfPageWidth : 0;

  const paintHighlights = useCallback(() => {
    const layer = pageWrapRef.current?.querySelector(".react-pdf__Page__textContent");
    if (layer instanceof HTMLElement) {
      const matched = applyPdfPageHighlights(layer, highlights, referenceText);
      onHighlightStatus?.(matched || bbox != null);
      return;
    }
    onHighlightStatus?.(bbox != null);
  }, [highlights, referenceText, bbox, onHighlightStatus]);

  useEffect(() => {
    paintHighlights();
    const raf = requestAnimationFrame(() => paintHighlights());
    const retry = window.setTimeout(() => paintHighlights(), 200);
    const retryLate = window.setTimeout(() => paintHighlights(), 600);
    const retryLate2 = window.setTimeout(() => paintHighlights(), 1200);

    const layer = pageWrapRef.current?.querySelector(".react-pdf__Page__textContent");
    let observer: MutationObserver | null = null;
    if (layer instanceof HTMLElement) {
      observer = new MutationObserver(() => paintHighlights());
      observer.observe(layer, { childList: true, subtree: true });
    }

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(retry);
      clearTimeout(retryLate);
      clearTimeout(retryLate2);
      observer?.disconnect();
    };
  }, [paintHighlights, pageNumber, pageWidth]);

  return (
    <div ref={pageWrapRef} className="relative inline-block max-w-full">
      <Page
        pageNumber={pageNumber}
        width={pageWidth}
        renderTextLayer
        renderAnnotationLayer={false}
        onLoadSuccess={(page) => setPdfPageWidth(page.originalWidth)}
        onRenderTextLayerSuccess={paintHighlights}
        className="max-w-full"
      />
      {bbox && scale > 0 && (
        <div
          className="absolute evidence-bbox-highlight pointer-events-none"
          style={{
            left: bbox.x0 * scale,
            top: bbox.y0 * scale,
            width: (bbox.x1 - bbox.x0) * scale,
            height: (bbox.y1 - bbox.y0) * scale,
          }}
        />
      )}
    </div>
  );
}

export function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const [searchParams] = useSearchParams();
  const pageFromUrl = parsePageParam(searchParams.get("page"));
  const highlightText = searchParams.get("highlight");
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(() => pageFromUrl ?? 1);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(true);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pageWidth, setPageWidth] = useState(760);
  const [pdfHighlightMatched, setPdfHighlightMatched] = useState(false);
  const pdfContainerRef = useRef<HTMLDivElement>(null);

  const locateQuery = useMemo(() => {
    const query: Record<string, string> = { text: highlightText! };
    if (pageFromUrl != null) query.page = String(pageFromUrl);
    return query;
  }, [highlightText, pageFromUrl]);

  const { data: locate, isLoading: locating } = useQuery({
    queryKey: ["document-locate", documentId, highlightText, pageFromUrl],
    queryFn: () =>
      api<SourceLocateResult>(`/documents/${documentId}/locate`, {
        query: locateQuery,
      }),
    enabled: !!documentId && !!highlightText?.trim(),
  });

  const targetPage = pageFromUrl ?? locate?.page ?? null;
  const sourceBbox = useMemo(() => parseSourceBbox(locate?.bbox), [locate?.bbox]);
  const highlights = useMemo(
    () => (highlightText ? buildEvidenceHighlights([highlightText]) : { patterns: [], quoteTexts: [] }),
    [highlightText],
  );

  useEffect(() => {
    if (targetPage != null) setPage(targetPage);
  }, [targetPage]);

  useEffect(() => {
    setPdfHighlightMatched(false);
  }, [highlightText, page, locate?.bbox]);

  useEffect(() => {
    const el = pdfContainerRef.current;
    if (!el) return;
    const update = () => setPageWidth(Math.max(240, el.clientWidth - 16));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [pdfUrl]);

  useEffect(() => {
    if (!documentId) return;
    const ac = new AbortController();
    setPdfLoading(true);
    setPdfError(null);
    apiBlob(`/documents/${documentId}/file`, { signal: ac.signal })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        setPdfUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
      })
      .catch((err) => {
        if (ac.signal.aborted) return;
        setPdfError(err instanceof Error ? err.message : "Failed to load PDF");
      })
      .finally(() => {
        if (!ac.signal.aborted) setPdfLoading(false);
      });
    return () => {
      ac.abort();
      setPdfUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [documentId]);

  const { data, isLoading } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api<DocumentDetail>(`/documents/${documentId}`),
    enabled: !!documentId,
  });

  if (isLoading || (highlightText?.trim() && locating)) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Document not found.</div>;

  const { document: doc, company, event } = data;
  const showHighlight = Boolean(
    highlightText?.trim() && (targetPage == null || page === targetPage),
  );
  const showMarkdownFallback =
    showHighlight &&
    Boolean(locate?.reference_text) &&
    !pdfHighlightMatched &&
    sourceBbox == null;

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <BackButton fallback="/companies" />

      <header className="card p-5 space-y-2">
        <h1 className="text-lg font-semibold text-ink leading-snug">
          {documentDisplayTitle(doc, event)}
        </h1>
        {company?.name && (
          <div className="text-sm text-ink-soft">{company.name}</div>
        )}
        {highlightText && (locate?.page ?? targetPage) && (
          <p className="text-xs text-ink-soft pt-1">
            Showing source on page {locate?.page ?? targetPage}
          </p>
        )}
      </header>

      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-ink-mute">
            Page {page} {numPages ? `of ${numPages}` : ""}
          </span>
          <div className="flex items-center gap-2">
            <button
              className="btn-secondary px-2 py-1"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              className="btn-secondary px-2 py-1"
              disabled={numPages > 0 && page >= numPages}
              onClick={() => setPage((p) => (numPages ? Math.min(numPages, p + 1) : p + 1))}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
        <div
          ref={pdfContainerRef}
          className="flex justify-center overflow-x-auto bg-bg-deep/40 rounded-xl p-2 w-full"
        >
          {pdfLoading ? (
            <div className="py-24">
              <Spinner size={20} />
            </div>
          ) : pdfError ? (
            <div className="py-24 text-sm text-negative">{pdfError}</div>
          ) : pdfUrl ? (
            <Document
              file={pdfUrl}
              onLoadSuccess={({ numPages }) => setNumPages(numPages)}
              loading={
                <div className="py-24">
                  <Spinner size={20} />
                </div>
              }
              error={<div className="py-24 text-sm text-negative">Failed to render PDF.</div>}
            >
              {showHighlight ? (
                <PdfPageWithHighlights
                  pageNumber={page}
                  pageWidth={pageWidth}
                  highlightText={highlightText}
                  referenceText={locate?.reference_text ?? null}
                  bbox={sourceBbox}
                  onHighlightStatus={setPdfHighlightMatched}
                />
              ) : (
                <Page
                  pageNumber={page}
                  width={pageWidth}
                  renderTextLayer
                  renderAnnotationLayer={false}
                  className="max-w-full"
                />
              )}
            </Document>
          ) : null}
        </div>

        {showMarkdownFallback && locate?.reference_text && (
          <div className="mt-4 rounded-xl border border-line/70 bg-surface/60 p-4 space-y-2">
            <p className="text-xs font-medium text-ink-soft">
              Parsed source excerpt
            </p>
            <p className="text-[11px] text-ink-mute">
              PDF text layer did not match — showing the parsed filing text instead.
            </p>
            <div
              className="text-xs text-ink leading-relaxed whitespace-pre-wrap font-mono max-h-64 overflow-y-auto"
              dangerouslySetInnerHTML={{
                __html: highlightMatchInText(locate.reference_text, highlights.patterns),
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
