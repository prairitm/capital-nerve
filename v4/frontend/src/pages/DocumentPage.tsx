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
import { buildEvidenceHighlights, applyPdfPageHighlights } from "@/lib/pdfHighlight";

pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorker;

function parsePageParam(raw: string | null): number | null {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function PdfPageWithHighlights({
  pageNumber,
  highlightText,
  referenceText,
}: {
  pageNumber: number;
  highlightText: string | null;
  referenceText: string | null;
}) {
  const pageWrapRef = useRef<HTMLDivElement>(null);
  const highlights = useMemo(
    () => (highlightText ? buildEvidenceHighlights([highlightText]) : { patterns: [], quoteTexts: [] }),
    [highlightText],
  );

  const paintHighlights = useCallback(() => {
    const layer = pageWrapRef.current?.querySelector(".react-pdf__Page__textContent");
    if (layer instanceof HTMLElement) {
      applyPdfPageHighlights(layer, highlights, referenceText);
    }
  }, [highlights, referenceText]);

  useEffect(() => {
    paintHighlights();
    const raf = requestAnimationFrame(() => paintHighlights());
    const retry = window.setTimeout(() => paintHighlights(), 200);
    const retryLate = window.setTimeout(() => paintHighlights(), 600);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(retry);
      clearTimeout(retryLate);
    };
  }, [paintHighlights, pageNumber]);

  return (
    <div ref={pageWrapRef}>
      <Page
        pageNumber={pageNumber}
        width={760}
        renderTextLayer
        renderAnnotationLayer={false}
        onRenderTextLayerSuccess={paintHighlights}
      />
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

  const { data: locate, isLoading: locating } = useQuery({
    queryKey: ["document-locate", documentId, highlightText],
    queryFn: () =>
      api<SourceLocateResult>(`/documents/${documentId}/locate`, {
        query: { text: highlightText! },
      }),
    enabled: !!documentId && !!highlightText?.trim(),
  });

  const targetPage = pageFromUrl ?? locate?.page ?? null;

  useEffect(() => {
    if (targetPage != null) setPage(targetPage);
  }, [targetPage]);

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
        {highlightText && locate?.page && (
          <p className="text-xs text-ink-soft pt-1">
            Showing source on page {locate.page}
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
        <div className="flex justify-center overflow-auto bg-bg-deep/40 rounded-xl p-2">
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
                  highlightText={highlightText}
                  referenceText={locate?.reference_text ?? null}
                />
              ) : (
                <Page
                  pageNumber={page}
                  width={760}
                  renderTextLayer
                  renderAnnotationLayer={false}
                />
              )}
            </Document>
          ) : null}
        </div>
      </div>
    </div>
  );
}
