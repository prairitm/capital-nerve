import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Document, Page, pdfjs } from "react-pdf";
import { ChevronLeft, ChevronRight, Maximize2, X } from "lucide-react";
import clsx from "clsx";
import { apiBlob } from "@/api/client";
import type { DocumentDetail } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import {
  evidenceHighlightPatterns,
  formatEvidenceValue,
  highlightMatchInText,
  type EvidenceHighlightInput,
} from "@/lib/format";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface Props {
  doc: DocumentDetail;
}

function isPdfDocument(doc: DocumentDetail): boolean {
  return (
    doc.has_source_file &&
    typeof doc.source_content_type === "string" &&
    doc.source_content_type.toLowerCase().includes("pdf")
  );
}

/** Lowest page number with mapped evidence; used when opening the viewer without `?page=`. */
function firstEvidencePage(doc: DocumentDetail): number | null {
  const pages = doc.evidence
    .map((e) => e.page_number)
    .filter((p): p is number => p != null && p > 0);
  if (pages.length === 0) return null;
  return Math.min(...pages);
}

function resolveTargetPage(doc: DocumentDetail, pageFromUrl: number): number {
  if (Number.isFinite(pageFromUrl) && pageFromUrl > 0) return pageFromUrl;
  return firstEvidencePage(doc) ?? doc.pages[0]?.page_number ?? 1;
}

export function EvidenceViewer({ doc }: Props) {
  const showPdf = isPdfDocument(doc);
  const [searchParams, setSearchParams] = useSearchParams();
  const pageFromUrl = Number(searchParams.get("page"));
  const hasUrlPage = Number.isFinite(pageFromUrl) && pageFromUrl > 0;
  const [activePage, setActivePage] = useState<number>(() => resolveTargetPage(doc, pageFromUrl));
  const scrollRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLElement>>(new Map());
  const initialScrollPending = useRef(true);

  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(showPdf);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfNumPages, setPdfNumPages] = useState(0);
  const [pageWidth, setPageWidth] = useState<number | undefined>(undefined);
  const [pdfExpanded, setPdfExpanded] = useState(false);

  const evidenceCountByPage = useMemo(() => {
    const counts = new Map<number, number>();
    for (const e of doc.evidence) {
      if (e.page_number == null) continue;
      counts.set(e.page_number, (counts.get(e.page_number) ?? 0) + 1);
    }
    return counts;
  }, [doc.evidence]);

  const evidenceByPage = useMemo(() => {
    const byPage = new Map<number, EvidenceHighlightInput[]>();
    for (const e of doc.evidence) {
      if (e.page_number == null) continue;
      const list = byPage.get(e.page_number) ?? [];
      list.push({ evidence_value: e.evidence_value, source_text: e.source_text });
      byPage.set(e.page_number, list);
    }
    return byPage;
  }, [doc.evidence]);

  const pageNumbers = useMemo(() => {
    if (showPdf) {
      if (pdfNumPages <= 0) return [];
      return Array.from({ length: pdfNumPages }, (_, i) => i + 1);
    }
    return doc.pages.map((p) => p.page_number);
  }, [showPdf, pdfNumPages, doc.pages]);

  const pageEvidence = doc.evidence.filter((e) => e.page_number === activePage);
  const totalPages = showPdf && pdfNumPages > 0 ? pdfNumPages : doc.page_count ?? doc.pages.length;

  useEffect(() => {
    if (!showPdf) return;
    const ac = new AbortController();
    setPdfLoading(true);
    setPdfError(null);
    apiBlob(`/documents/${doc.document_id}/file`, { signal: ac.signal })
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
  }, [doc.document_id, showPdf]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => setPageWidth(Math.max(240, el.clientWidth - 40));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [showPdf, pdfUrl]);

  useEffect(() => {
    initialScrollPending.current = true;
    const target = resolveTargetPage(doc, pageFromUrl);
    setActivePage(target);
    if (!hasUrlPage && target > 1) {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("page", String(target));
          return next;
        },
        { replace: true },
      );
    }
  }, [doc.document_id, pageFromUrl, hasUrlPage, doc.evidence, doc.pages, setSearchParams]);

  const syncPageToUrl = useCallback(
    (pageNumber: number) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (pageNumber <= 1) {
            next.delete("page");
          } else {
            next.set("page", String(pageNumber));
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const selectPage = useCallback(
    (pageNumber: number) => {
      setActivePage(pageNumber);
      syncPageToUrl(pageNumber);
      pageRefs.current.get(pageNumber)?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    [syncPageToUrl],
  );

  useEffect(() => {
    const root = scrollRef.current;
    if (!root || pageNumbers.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const top = visible[0];
        if (!top) return;
        if (initialScrollPending.current) return;
        const pageNumber = Number(top.target.getAttribute("data-page-number"));
        if (!Number.isFinite(pageNumber) || pageNumber === activePage) return;
        setActivePage(pageNumber);
        syncPageToUrl(pageNumber);
      },
      { root, rootMargin: "-20% 0px -55% 0px", threshold: [0, 0.25, 0.5, 0.75, 1] },
    );

    for (const el of pageRefs.current.values()) {
      observer.observe(el);
    }
    return () => observer.disconnect();
  }, [pageNumbers, activePage, syncPageToUrl]);

  useEffect(() => {
    if (!initialScrollPending.current) return;
    if (showPdf && (pdfLoading || pdfNumPages <= 0)) return;
    if (pageNumbers.length === 0) return;

    const el = pageRefs.current.get(activePage);
    if (!el) return;

    const id = requestAnimationFrame(() => {
      el.scrollIntoView({ block: "start" });
      initialScrollPending.current = false;
    });
    return () => cancelAnimationFrame(id);
  }, [activePage, pdfLoading, pdfNumPages, pageNumbers, showPdf, doc.document_id]);

  const registerPageRef = useCallback((pageNumber: number, el: HTMLElement | null) => {
    if (el) pageRefs.current.set(pageNumber, el);
    else pageRefs.current.delete(pageNumber);
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Document viewer */}
      <div className="card overflow-hidden flex flex-col min-h-0">
        <div className="px-4 py-3 border-b border-line/70 flex items-center justify-between flex-wrap gap-2 shrink-0">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">Source Document</div>
            <h3 className="text-sm font-semibold">{doc.document_title}</h3>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-xs text-ink-mute tabular-nums">
              {totalPages > 0 ? (
                <>
                  Page {activePage} of {totalPages}
                  {showPdf && <span className="ml-1.5 text-ink-soft">· PDF</span>}
                </>
              ) : (
                "—"
              )}
            </div>
            {showPdf && !pdfLoading && pdfUrl && (
              <button
                type="button"
                onClick={() => setPdfExpanded(true)}
                className="btn-ghost px-2 py-1.5 text-xs"
                aria-label="Expand PDF to full screen"
                title="Full screen"
              >
                <Maximize2 size={15} />
              </button>
            )}
          </div>
        </div>

        <div className="flex min-h-0 flex-1">
          <nav
            className="hidden sm:flex flex-col gap-0.5 w-14 shrink-0 border-r border-line/70 py-3 px-1.5 overflow-y-auto max-h-[70vh] scrollbar-none"
            aria-label="Page index"
          >
            {pageNumbers.map((pageNumber) => {
              const count = evidenceCountByPage.get(pageNumber) ?? 0;
              return (
                <button
                  key={pageNumber}
                  type="button"
                  onClick={() => selectPage(pageNumber)}
                  title={
                    count > 0
                      ? `Page ${pageNumber} · ${count} evidence item${count === 1 ? "" : "s"}`
                      : `Page ${pageNumber}`
                  }
                  className={clsx(
                    "relative flex flex-col items-center rounded-lg py-1.5 text-[10px] font-medium transition-colors",
                    pageNumber === activePage
                      ? "btn-brand-active"
                      : "text-ink-mute hover:text-ink hover:bg-surface-2",
                  )}
                >
                  <span>{pageNumber}</span>
                  {count > 0 && (
                    <span
                      className={clsx(
                        "mt-0.5 size-1.5 rounded-full",
                        pageNumber === activePage ? "bg-ink" : "bg-positive",
                      )}
                      aria-hidden
                    />
                  )}
                </button>
              );
            })}
          </nav>

          <div
            ref={scrollRef}
            className="flex-1 overflow-x-auto overflow-y-auto max-h-[70vh] p-4 space-y-6 bg-bg-deep/40"
          >
            {showPdf ? (
              <PdfDocumentStack
                pdfUrl={pdfUrl}
                pdfLoading={pdfLoading}
                pdfError={pdfError}
                pageWidth={pageWidth}
                pageNumbers={pageNumbers}
                activePage={activePage}
                evidenceCountByPage={evidenceCountByPage}
                evidenceByPage={evidenceByPage}
                registerPageRef={registerPageRef}
                onDocumentLoad={setPdfNumPages}
              />
            ) : (
              <TextDocumentStack
                doc={doc}
                activePage={activePage}
                evidenceCountByPage={evidenceCountByPage}
                evidenceByPage={evidenceByPage}
                registerPageRef={registerPageRef}
              />
            )}
          </div>
        </div>

        <div className="sm:hidden flex items-center gap-1 px-3 py-2 border-t border-line/70 overflow-x-auto scrollbar-none">
          {pageNumbers.map((pageNumber) => (
            <button
              key={pageNumber}
              type="button"
              onClick={() => selectPage(pageNumber)}
              className={clsx(
                "shrink-0 rounded-lg px-2.5 py-1 text-xs",
                pageNumber === activePage
                  ? "btn-brand-active"
                  : "bg-surface-2 text-ink-mute hover:text-ink",
              )}
            >
              {pageNumber}
              {(evidenceCountByPage.get(pageNumber) ?? 0) > 0 && (
                <span className="ml-1 text-positive">·</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Evidence panel */}
      <div className="space-y-4">
        <div className="card p-4">
          <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-1">
            Highlighted on page {activePage}
          </div>
          <p className="text-xs text-ink-mute mb-3">
            Evidence rows mapped to this page number in the source filing.
          </p>
          {pageEvidence.length === 0 ? (
            <p className="text-sm text-ink-mute">No extracted evidence highlighted on this page.</p>
          ) : (
            <div className="space-y-2">
              {pageEvidence.map((e) => {
                const displayValue = formatEvidenceValue(e.evidence_value);
                return (
                <div key={e.card_evidence_id} className="card-2 p-3">
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-sm font-medium">{e.evidence_label}</div>
                    {e.confidence_score !== null && (
                      <span className="text-[11px] text-ink-soft">{e.confidence_score.toFixed(0)}%</span>
                    )}
                  </div>
                  {displayValue && <div className="text-sm num">{displayValue}</div>}
                  {e.source_text && (
                    <p className="mt-2 text-xs text-ink-mute italic border-l-2 border-line pl-3">
                      "{e.source_text}"
                    </p>
                  )}
                  {e.calculation_text && (
                    <p className="mt-1.5 text-xs text-ink-mute font-mono">{e.calculation_text}</p>
                  )}
                </div>
              );
              })}
            </div>
          )}
        </div>

        <div className="card p-4">
          <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-2">Document Metadata</div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Meta label="Type" value={doc.document_type.replace(/_/g, " ")} />
            <Meta label="Date" value={doc.document_date ? new Date(doc.document_date).toLocaleDateString() : "—"} />
            <Meta label="Pages" value={String(totalPages || "—")} />
            <Meta
              label="Confidence"
              value={doc.extraction_confidence ? `${doc.extraction_confidence.toFixed(1)}%` : "—"}
            />
            <Meta label="Values extracted" value={String(doc.values_extracted ?? "—")} />
            <Meta label="Insights surfaced" value={String(doc.cards_generated ?? "—")} />
          </div>
        </div>

        {doc.cards.length > 0 && (
          <div className="card p-4">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-1">
              Insights from this filing
            </div>
            <p className="text-xs text-ink-mute mb-3">
              Each insight links back to evidence in this document.
            </p>
            <div className="space-y-2">
              {doc.cards.map((c) => (
                <div key={c.card_id} className="card-2 p-3">
                  <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                    {c.card_type.replace(/_/g, " ")}
                  </div>
                  <div className="text-sm font-medium">{c.headline}</div>
                  <div className="text-xs text-ink-mute mt-0.5">{c.one_line_summary}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {pdfExpanded && showPdf && (
        <PdfFullscreenOverlay
          documentTitle={doc.document_title}
          pdfUrl={pdfUrl}
          pdfLoading={pdfLoading}
          pdfError={pdfError}
          pageNumbers={pageNumbers}
          activePage={activePage}
          totalPages={totalPages}
          evidenceCountByPage={evidenceCountByPage}
          evidenceByPage={evidenceByPage}
          onClose={() => setPdfExpanded(false)}
          onSelectPage={selectPage}
          onDocumentLoad={setPdfNumPages}
        />
      )}
    </div>
  );
}

function PdfFullscreenOverlay({
  documentTitle,
  pdfUrl,
  pdfLoading,
  pdfError,
  pageNumbers,
  activePage,
  totalPages,
  evidenceCountByPage,
  evidenceByPage,
  onClose,
  onSelectPage,
  onDocumentLoad,
}: {
  documentTitle: string;
  pdfUrl: string | null;
  pdfLoading: boolean;
  pdfError: string | null;
  pageNumbers: number[];
  activePage: number;
  totalPages: number;
  pageWidth: number | undefined;
  evidenceCountByPage: Map<number, number>;
  evidenceByPage: Map<number, EvidenceHighlightInput[]>;
  onClose: () => void;
  onSelectPage: (pageNumber: number) => void;
  onDocumentLoad: (numPages: number) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLElement>>(new Map());
  const [overlayPageWidth, setOverlayPageWidth] = useState<number | undefined>(undefined);

  const registerPageRef = useCallback((pageNumber: number, el: HTMLElement | null) => {
    if (el) pageRefs.current.set(pageNumber, el);
    else pageRefs.current.delete(pageNumber);
  }, []);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () =>
      setOverlayPageWidth(Math.max(320, Math.min(960, el.clientWidth - 48)));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (pdfLoading || pageNumbers.length === 0) return;
    const id = requestAnimationFrame(() => {
      pageRefs.current.get(activePage)?.scrollIntoView({ block: "start" });
    });
    return () => cancelAnimationFrame(id);
  }, [pdfLoading, pageNumbers.length, activePage]);

  const goPrev = () => {
    if (activePage > 1) onSelectPage(activePage - 1);
  };
  const goNext = () => {
    if (activePage < totalPages) onSelectPage(activePage + 1);
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-stretch justify-center p-0 sm:p-4"
      role="dialog"
      aria-modal
      aria-label="PDF full screen view"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        aria-label="Close full screen"
        onClick={onClose}
      />
      <div className="relative flex flex-col w-full h-full sm:max-h-[calc(100vh-2rem)] sm:rounded-2xl border border-line bg-bg shadow-2xl overflow-hidden min-h-0">
        <header className="shrink-0 flex items-center justify-between gap-3 px-4 py-3 border-b border-line/70 bg-bg/95 backdrop-blur">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">Source Document</div>
            <h3 className="text-sm font-semibold truncate">{documentTitle}</h3>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={goPrev}
              disabled={activePage <= 1}
              className="btn-ghost p-2 disabled:opacity-40"
              aria-label="Previous page"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="text-xs text-ink-mute tabular-nums min-w-[5.5rem] text-center">
              Page {activePage} of {totalPages || "—"}
            </span>
            <button
              type="button"
              onClick={goNext}
              disabled={activePage >= totalPages}
              className="btn-ghost p-2 disabled:opacity-40"
              aria-label="Next page"
            >
              <ChevronRight size={18} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="btn-ghost p-2 ml-1"
              aria-label="Close full screen"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        <div className="flex flex-1 min-h-0">
          <nav
            className="hidden sm:flex flex-col gap-0.5 w-14 shrink-0 border-r border-line/70 py-3 px-1.5 overflow-y-auto scrollbar-none"
            aria-label="Page index"
          >
            {pageNumbers.map((pageNumber) => {
              const count = evidenceCountByPage.get(pageNumber) ?? 0;
              return (
                <button
                  key={pageNumber}
                  type="button"
                  onClick={() => onSelectPage(pageNumber)}
                  title={
                    count > 0
                      ? `Page ${pageNumber} · ${count} evidence item${count === 1 ? "" : "s"}`
                      : `Page ${pageNumber}`
                  }
                  className={clsx(
                    "relative flex flex-col items-center rounded-lg py-1.5 text-[10px] font-medium transition-colors",
                    pageNumber === activePage
                      ? "btn-brand-active"
                      : "text-ink-mute hover:text-ink hover:bg-surface-2",
                  )}
                >
                  <span>{pageNumber}</span>
                  {count > 0 && (
                    <span
                      className={clsx(
                        "mt-0.5 size-1.5 rounded-full",
                        pageNumber === activePage ? "bg-ink" : "bg-positive",
                      )}
                      aria-hidden
                    />
                  )}
                </button>
              );
            })}
          </nav>

          <div
            ref={scrollRef}
            className="flex-1 overflow-x-auto overflow-y-auto p-4 sm:p-6 space-y-6 bg-bg-deep/40 min-h-0"
          >
            <PdfDocumentStack
              pdfUrl={pdfUrl}
              pdfLoading={pdfLoading}
              pdfError={pdfError}
              pageWidth={overlayPageWidth}
              pageNumbers={pageNumbers}
              activePage={activePage}
              evidenceCountByPage={evidenceCountByPage}
              evidenceByPage={evidenceByPage}
              registerPageRef={registerPageRef}
              onDocumentLoad={onDocumentLoad}
            />
          </div>
        </div>

        <div className="sm:hidden flex items-center gap-1 px-3 py-2 border-t border-line/70 overflow-x-auto scrollbar-none shrink-0">
          {pageNumbers.map((pageNumber) => (
            <button
              key={pageNumber}
              type="button"
              onClick={() => onSelectPage(pageNumber)}
              className={clsx(
                "shrink-0 rounded-lg px-2.5 py-1 text-xs",
                pageNumber === activePage
                  ? "btn-brand-active"
                  : "bg-surface-2 text-ink-mute hover:text-ink",
              )}
            >
              {pageNumber}
              {(evidenceCountByPage.get(pageNumber) ?? 0) > 0 && (
                <span className="ml-1 text-positive">·</span>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function PdfDocumentStack({
  pdfUrl,
  pdfLoading,
  pdfError,
  pageWidth,
  pageNumbers,
  activePage,
  evidenceCountByPage,
  evidenceByPage,
  registerPageRef,
  onDocumentLoad,
}: {
  pdfUrl: string | null;
  pdfLoading: boolean;
  pdfError: string | null;
  pageWidth: number | undefined;
  pageNumbers: number[];
  activePage: number;
  evidenceCountByPage: Map<number, number>;
  evidenceByPage: Map<number, EvidenceHighlightInput[]>;
  registerPageRef: (pageNumber: number, el: HTMLElement | null) => void;
  onDocumentLoad: (numPages: number) => void;
}) {
  if (pdfLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <PageLoader />
      </div>
    );
  }
  if (pdfError) {
    return <p className="text-sm text-negative p-2">{pdfError}</p>;
  }
  if (!pdfUrl) {
    return <p className="text-sm text-ink-mute p-2">PDF file unavailable.</p>;
  }

  return (
    <Document
      file={pdfUrl}
      loading={
        <div className="flex items-center justify-center py-12">
          <PageLoader />
        </div>
      }
      onLoadSuccess={({ numPages }) => onDocumentLoad(numPages)}
      onLoadError={() => onDocumentLoad(0)}
      className="space-y-6"
    >
      {pageNumbers.map((pageNumber) => {
        const evidenceOnPage = evidenceCountByPage.get(pageNumber) ?? 0;
        return (
          <section
            key={pageNumber}
            ref={(el) => registerPageRef(pageNumber, el)}
            data-page-number={pageNumber}
            className={clsx(
              "scroll-mt-4 rounded-xl border bg-surface shadow-card transition-shadow overflow-hidden",
              pageNumber === activePage
                ? "border-line-strong ring-1 ring-line-strong/80"
                : "border-line/80",
            )}
          >
            <header className="flex items-center justify-between gap-2 border-b border-line/70 bg-surface/95 px-4 py-2.5">
              <span className="text-[11px] uppercase tracking-wider font-medium text-ink-soft">
                Page {pageNumber}
              </span>
              {evidenceOnPage > 0 ? (
                <span className="chip-neutral text-[10px]">{evidenceOnPage} evidence</span>
              ) : (
                <span className="text-[10px] text-ink-soft">No evidence mapped</span>
              )}
            </header>
            <div className="flex justify-center bg-[#1a1f2e] px-2 py-4">
              <PdfPageWithHighlights
                pageNumber={pageNumber}
                pageWidth={pageWidth}
                pageEvidence={evidenceByPage.get(pageNumber) ?? []}
              />
            </div>
          </section>
        );
      })}
    </Document>
  );
}

function PdfPageWithHighlights({
  pageNumber,
  pageWidth,
  pageEvidence,
}: {
  pageNumber: number;
  pageWidth: number | undefined;
  pageEvidence: EvidenceHighlightInput[];
}) {
  const patterns = useMemo(() => evidenceHighlightPatterns(pageEvidence), [pageEvidence]);
  const customTextRenderer = useCallback(
    (item: { str: string }) => highlightMatchInText(item.str, patterns),
    [patterns],
  );

  return (
    <Page
      pageNumber={pageNumber}
      width={pageWidth}
      renderTextLayer
      renderAnnotationLayer
      className="shadow-card"
      customTextRenderer={patterns.length > 0 ? customTextRenderer : undefined}
    />
  );
}

function TextDocumentStack({
  doc,
  activePage,
  evidenceCountByPage,
  evidenceByPage,
  registerPageRef,
}: {
  doc: DocumentDetail;
  activePage: number;
  evidenceCountByPage: Map<number, number>;
  evidenceByPage: Map<number, EvidenceHighlightInput[]>;
  registerPageRef: (pageNumber: number, el: HTMLElement | null) => void;
}) {
  if (doc.pages.length === 0) {
    return <p className="text-sm text-ink-mute p-2">No pages available for this document.</p>;
  }

  return (
    <>
      {doc.pages.map((p) => {
        const content = p.page_markdown || p.page_text || "";
        const evidenceOnPage = evidenceCountByPage.get(p.page_number) ?? 0;
        return (
          <section
            key={p.page_id}
            ref={(el) => registerPageRef(p.page_number, el)}
            data-page-number={p.page_number}
            className={clsx(
              "scroll-mt-4 rounded-xl border bg-surface shadow-card transition-shadow",
              p.page_number === activePage
                ? "border-line-strong ring-1 ring-line-strong/80"
                : "border-line/80",
            )}
          >
            <header className="sticky top-0 z-[1] flex items-center justify-between gap-2 rounded-t-xl border-b border-line/70 bg-surface/95 backdrop-blur px-4 py-2.5">
              <span className="text-[11px] uppercase tracking-wider font-medium text-ink-soft">
                Page {p.page_number}
              </span>
              {evidenceOnPage > 0 ? (
                <span className="chip-neutral text-[10px]">{evidenceOnPage} evidence</span>
              ) : (
                <span className="text-[10px] text-ink-soft">No evidence mapped</span>
              )}
            </header>
            <div className="px-4 py-5">
              <DocumentPageContent
                content={content}
                highlightPatterns={evidenceHighlightPatterns(
                  evidenceByPage.get(p.page_number) ?? [],
                )}
              />
            </div>
          </section>
        );
      })}
    </>
  );
}

function DocumentPageContent({
  content,
  highlightPatterns,
}: {
  content: string;
  highlightPatterns: string[];
}) {
  if (!content.trim()) {
    return <p className="text-sm text-ink-mute italic">No extractable text on this page.</p>;
  }
  if (looksLikeMarkdown(content)) {
    return (
      <article className="max-w-none">
        <MarkdownLite content={content} highlightPatterns={highlightPatterns} />
      </article>
    );
  }
  if (highlightPatterns.length > 0) {
    return (
      <div
        className="text-sm text-ink-mute leading-relaxed whitespace-pre-wrap break-words font-sans"
        dangerouslySetInnerHTML={{ __html: highlightMatchInText(content, highlightPatterns) }}
      />
    );
  }
  return (
    <div className="text-sm text-ink-mute leading-relaxed whitespace-pre-wrap break-words font-sans">
      {content}
    </div>
  );
}

function looksLikeMarkdown(content: string): boolean {
  const lines = content.split("\n");
  for (const line of lines) {
    const t = line.trim();
    if (t.startsWith("# ") || t.startsWith("## ")) return true;
    if (t.startsWith("|") && t.endsWith("|")) return true;
    if (t.startsWith("- ") || t.startsWith("* ")) return true;
    if (/^\*\*.+\*\*$/.test(t)) return true;
  }
  return false;
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-ink-soft">{label}</div>
      <div className="text-sm text-ink">{value}</div>
    </div>
  );
}

function MarkdownLite({
  content,
  highlightPatterns = [],
}: {
  content: string;
  highlightPatterns?: string[];
}) {
  const lines = content.split("\n");
  const blocks: JSX.Element[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("## ")) {
      blocks.push(
        <h3 key={i} className="text-base font-semibold text-ink mt-4 mb-2">
          {line.replace(/^##\s+/, "")}
        </h3>,
      );
      i++;
      continue;
    }
    if (line.startsWith("# ")) {
      blocks.push(
        <h2 key={i} className="text-lg font-semibold text-ink mt-1 mb-2">
          {line.replace(/^#\s+/, "")}
        </h2>,
      );
      i++;
      continue;
    }
    if (line.startsWith("|") && lines[i + 1]?.startsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      blocks.push(renderTable(tableLines, "tbl-" + i));
      continue;
    }
    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(lines[i].replace(/^-\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={i} className="list-disc list-inside text-sm text-ink-mute space-y-1 my-2">
          {items.map((it, idx) => (
            <li key={idx} dangerouslySetInnerHTML={{ __html: renderInline(it) }} />
          ))}
        </ul>,
      );
      continue;
    }
    if (line.trim() === "") {
      i++;
      continue;
    }
    const lineHtml =
      highlightPatterns.length > 0 && !line.includes("**")
        ? highlightMatchInText(line, highlightPatterns)
        : renderInline(line);
    blocks.push(
      <p
        key={i}
        className="text-sm text-ink-mute leading-relaxed my-1.5"
        dangerouslySetInnerHTML={{ __html: lineHtml }}
      />,
    );
    i++;
  }
  return <>{blocks}</>;
}

function renderInline(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-ink">$1</strong>');
}

function renderTable(lines: string[], key: string) {
  const rows = lines.map((l) =>
    l
      .trim()
      .replace(/^\||\|$/g, "")
      .split("|")
      .map((c) => c.trim()),
  );
  if (rows.length < 2) return <div key={key} />;
  const [head, , ...body] = rows;
  return (
    <div key={key} className="overflow-x-auto my-3">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-ink-soft uppercase tracking-wider text-[10px]">
            {head.map((h, i) => (
              <th key={i} className="px-2 py-1.5 font-medium border-b border-line">
                <span dangerouslySetInnerHTML={{ __html: renderInline(h) }} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, i) => (
            <tr key={i} className="border-b border-line/40">
              {r.map((c, j) => (
                <td
                  key={j}
                  className={clsx(
                    "px-2 py-1.5 text-ink num",
                    j === 0 ? "text-ink-mute" : "text-right",
                  )}
                  dangerouslySetInnerHTML={{ __html: renderInline(c) }}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
