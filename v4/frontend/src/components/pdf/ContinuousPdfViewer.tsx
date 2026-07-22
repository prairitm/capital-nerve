import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import { Document, Page } from "react-pdf";
import type { SourceBbox, PdfHighlightResult } from "@/lib/pdfHighlight";
import { applyPdfPageHighlights, buildEvidenceHighlights } from "@/lib/pdfHighlight";
import { Spinner } from "@/components/common/Spinner";

const DEFAULT_PAGE_RATIO = 1.4142;
const PAGE_RENDER_MARGIN = "1200px 0px";

export type ContinuousPdfViewerHandle = {
  scrollToPage: (pageNumber: number, behavior?: ScrollBehavior) => void;
  scrollToEvidence: () => void;
};

type ContinuousPdfViewerProps = {
  file: string;
  pageWidth: number;
  targetPage: number | null;
  highlightKey: string | null;
  highlightText: string | null;
  highlightValue: string | null;
  referenceText: string | null;
  bbox: SourceBbox | null;
  onDocumentLoad: (numPages: number) => void;
  onCurrentPageChange: (pageNumber: number) => void;
  onHighlightStatus: (matched: boolean) => void;
};

function scrollElementWithinViewer(
  viewer: HTMLElement,
  element: HTMLElement,
  behavior: ScrollBehavior,
  center: boolean,
) {
  const viewerRect = viewer.getBoundingClientRect();
  const elementRect = element.getBoundingClientRect();
  const relativeTop = elementRect.top - viewerRect.top + viewer.scrollTop;
  const top = center
    ? relativeTop - viewer.clientHeight / 2 + elementRect.height / 2
    : relativeTop - 24;
  viewer.scrollTo({ top: Math.max(0, top), behavior });
}

export const ContinuousPdfViewer = forwardRef<
  ContinuousPdfViewerHandle,
  ContinuousPdfViewerProps
>(function ContinuousPdfViewer(
  {
    file,
    pageWidth,
    targetPage,
    highlightKey,
    highlightText,
    highlightValue,
    referenceText,
    bbox,
    onDocumentLoad,
    onCurrentPageChange,
    onHighlightStatus,
  },
  ref,
) {
  const viewerRef = useRef<HTMLDivElement>(null);
  const pageElementsRef = useRef(new Map<number, HTMLElement>());
  const evidenceTargetRef = useRef<HTMLElement | null>(null);
  const pageScrollKeyRef = useRef<string | null>(null);
  const evidenceScrollKeyRef = useRef<string | null>(null);
  const [numPages, setNumPages] = useState(0);

  const scrollToPage = useCallback((pageNumber: number, behavior: ScrollBehavior = "smooth") => {
    const viewer = viewerRef.current;
    const pageElement = pageElementsRef.current.get(pageNumber);
    if (!viewer || !pageElement) return;
    scrollElementWithinViewer(viewer, pageElement, behavior, false);
  }, []);

  const scrollToEvidence = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    if (evidenceTargetRef.current) {
      scrollElementWithinViewer(viewer, evidenceTargetRef.current, "smooth", true);
      return;
    }
    if (targetPage != null) scrollToPage(targetPage);
  }, [scrollToPage, targetPage]);

  useImperativeHandle(
    ref,
    () => ({ scrollToPage, scrollToEvidence }),
    [scrollToEvidence, scrollToPage],
  );

  const registerPageElement = useCallback((pageNumber: number, element: HTMLElement | null) => {
    if (element) pageElementsRef.current.set(pageNumber, element);
    else pageElementsRef.current.delete(pageNumber);
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || numPages === 0 || typeof IntersectionObserver === "undefined") return;

    const visibleRatios = new Map<number, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const pageNumber = Number((entry.target as HTMLElement).dataset.pdfPage);
          if (!Number.isFinite(pageNumber)) continue;
          if (entry.isIntersecting) visibleRatios.set(pageNumber, entry.intersectionRatio);
          else visibleRatios.delete(pageNumber);
        }

        let mostVisiblePage: number | null = null;
        let bestRatio = -1;
        for (const [pageNumber, ratio] of visibleRatios) {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            mostVisiblePage = pageNumber;
          }
        }
        if (mostVisiblePage != null) onCurrentPageChange(mostVisiblePage);
      },
      {
        root: viewer,
        threshold: [0.05, 0.2, 0.4, 0.6, 0.8, 1],
      },
    );

    for (const element of pageElementsRef.current.values()) observer.observe(element);
    return () => observer.disconnect();
  }, [numPages, onCurrentPageChange]);

  useEffect(() => {
    if (targetPage == null || numPages === 0) return;
    const key = highlightKey ?? `page:${targetPage}`;
    if (pageScrollKeyRef.current === key) return;
    pageScrollKeyRef.current = key;
    evidenceScrollKeyRef.current = null;
    evidenceTargetRef.current = null;

    const frame = requestAnimationFrame(() => scrollToPage(targetPage, "auto"));
    return () => cancelAnimationFrame(frame);
  }, [highlightKey, numPages, scrollToPage, targetPage]);

  const handleHighlightResult = useCallback(
    (result: PdfHighlightResult) => {
      onHighlightStatus(result.matched);
      if (!result.matched || !result.target) return;
      evidenceTargetRef.current = result.target;

      const key = highlightKey ?? "evidence";
      if (evidenceScrollKeyRef.current === key) return;
      evidenceScrollKeyRef.current = key;
      const viewer = viewerRef.current;
      if (viewer) scrollElementWithinViewer(viewer, result.target, "smooth", true);
    },
    [highlightKey, onHighlightStatus],
  );

  const pages = useMemo(
    () => Array.from({ length: numPages }, (_, index) => index + 1),
    [numPages],
  );
  const highlightedPage = targetPage ?? 1;

  return (
    <div
      ref={viewerRef}
      className="pdf-scroll-viewport relative h-full overflow-auto bg-bg-deep/75 overscroll-contain"
      data-testid="pdf-scroll-viewport"
    >
      <Document
        file={file}
        onLoadSuccess={({ numPages: loadedPages }) => {
          setNumPages(loadedPages);
          onDocumentLoad(loadedPages);
        }}
        loading={
          <div className="grid min-h-full place-items-center py-24">
            <Spinner size={22} />
          </div>
        }
        error={
          <div className="grid min-h-full place-items-center py-24 text-sm text-negative">
            Failed to render PDF.
          </div>
        }
      >
        <div className="mx-auto flex min-w-max flex-col items-center gap-5 px-3 py-6 md:gap-7 md:px-8 md:py-8">
          {pages.map((pageNumber) => (
            <PdfPageFrame
              key={pageNumber}
              pageNumber={pageNumber}
              pageWidth={pageWidth}
              viewportRef={viewerRef}
              registerPageElement={registerPageElement}
              eager={pageNumber <= 2 || pageNumber === highlightedPage}
              highlightText={pageNumber === highlightedPage ? highlightText : null}
              highlightValue={pageNumber === highlightedPage ? highlightValue : null}
              referenceText={pageNumber === highlightedPage ? referenceText : null}
              bbox={pageNumber === highlightedPage ? bbox : null}
              onHighlightResult={pageNumber === highlightedPage ? handleHighlightResult : undefined}
            />
          ))}
        </div>
      </Document>
    </div>
  );
});

type PdfPageFrameProps = {
  pageNumber: number;
  pageWidth: number;
  viewportRef: MutableRefObject<HTMLDivElement | null>;
  registerPageElement: (pageNumber: number, element: HTMLElement | null) => void;
  eager: boolean;
  highlightText: string | null;
  highlightValue: string | null;
  referenceText: string | null;
  bbox: SourceBbox | null;
  onHighlightResult?: (result: PdfHighlightResult) => void;
};

function PdfPageFrame({
  pageNumber,
  pageWidth,
  viewportRef,
  registerPageElement,
  eager,
  highlightText,
  highlightValue,
  referenceText,
  bbox,
  onHighlightResult,
}: PdfPageFrameProps) {
  const wrapperRef = useRef<HTMLElement | null>(null);
  const [shouldRender, setShouldRender] = useState(eager);
  const [pageRatio, setPageRatio] = useState(DEFAULT_PAGE_RATIO);
  const [rendered, setRendered] = useState(false);

  const setWrapperRef = useCallback(
    (element: HTMLElement | null) => {
      wrapperRef.current = element;
      registerPageElement(pageNumber, element);
    },
    [pageNumber, registerPageElement],
  );

  useEffect(() => {
    if (eager) setShouldRender(true);
  }, [eager]);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    const viewport = viewportRef.current;
    if (!wrapper || !viewport || shouldRender || typeof IntersectionObserver === "undefined") {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setShouldRender(true);
          observer.disconnect();
        }
      },
      { root: viewport, rootMargin: PAGE_RENDER_MARGIN },
    );
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, [shouldRender, viewportRef]);

  const placeholderHeight = Math.round(pageWidth * pageRatio);
  const handlePageLoad = useCallback((page: { originalWidth: number; originalHeight: number }) => {
    if (page.originalWidth > 0 && page.originalHeight > 0) {
      setPageRatio(page.originalHeight / page.originalWidth);
    }
  }, []);

  return (
    <section
      ref={setWrapperRef}
      data-pdf-page={pageNumber}
      aria-label={`PDF page ${pageNumber}`}
      className="pdf-page-frame relative shrink-0"
      style={{
        width: pageWidth,
        minHeight: rendered ? undefined : placeholderHeight,
      }}
    >
      <div className="pdf-page-number" aria-hidden>
        {pageNumber}
      </div>
      {shouldRender ? (
        highlightText ? (
          <PdfPageWithHighlights
            pageNumber={pageNumber}
            pageWidth={pageWidth}
            highlightText={highlightText}
            highlightValue={highlightValue}
            referenceText={referenceText}
            bbox={bbox}
            onLoadSuccess={handlePageLoad}
            onRenderSuccess={() => setRendered(true)}
            onHighlightResult={onHighlightResult}
          />
        ) : (
          <Page
            pageNumber={pageNumber}
            width={pageWidth}
            renderTextLayer
            renderAnnotationLayer={false}
            onLoadSuccess={handlePageLoad}
            onRenderSuccess={() => setRendered(true)}
            loading={<PdfPagePlaceholder height={placeholderHeight} />}
            error={<PdfPageError pageNumber={pageNumber} height={placeholderHeight} />}
            className="max-w-full"
          />
        )
      ) : (
        <PdfPagePlaceholder height={placeholderHeight} />
      )}
    </section>
  );
}

function PdfPageWithHighlights({
  pageNumber,
  pageWidth,
  highlightText,
  highlightValue,
  referenceText,
  bbox,
  onLoadSuccess,
  onRenderSuccess,
  onHighlightResult,
}: {
  pageNumber: number;
  pageWidth: number;
  highlightText: string;
  highlightValue: string | null;
  referenceText: string | null;
  bbox: SourceBbox | null;
  onLoadSuccess: (page: { originalWidth: number; originalHeight: number }) => void;
  onRenderSuccess: () => void;
  onHighlightResult?: (result: PdfHighlightResult) => void;
}) {
  const pageWrapRef = useRef<HTMLDivElement>(null);
  const bboxRef = useRef<HTMLDivElement>(null);
  const [pdfPageWidth, setPdfPageWidth] = useState(0);
  const highlights = useMemo(
    () => buildEvidenceHighlights([highlightText], highlightValue),
    [highlightText, highlightValue],
  );
  const scale = pdfPageWidth > 0 ? pageWidth / pdfPageWidth : 0;
  const bboxPaddingX = 3;
  const bboxPaddingY = 2;

  const paintHighlights = useCallback(() => {
    const layer = pageWrapRef.current?.querySelector(".react-pdf__Page__textContent");
    if (!(layer instanceof HTMLElement)) {
      onHighlightResult?.({ matched: bbox != null, target: bboxRef.current });
      return;
    }
    if (bbox) {
      const spans = [...layer.querySelectorAll('[role="presentation"]')] as HTMLElement[];
      spans.forEach((element) => element.classList.remove("evidence-highlight"));
      layer.querySelectorAll(".evidence-value-highlight").forEach((element) => element.remove());
      onHighlightResult?.({ matched: true, target: bboxRef.current });
      return;
    }
    onHighlightResult?.(applyPdfPageHighlights(layer, highlights, referenceText));
  }, [bbox, highlights, onHighlightResult, referenceText]);

  useEffect(() => {
    paintHighlights();
    const frame = requestAnimationFrame(paintHighlights);
    const retries = [200, 600, 1200].map((delay) => window.setTimeout(paintHighlights, delay));

    return () => {
      cancelAnimationFrame(frame);
      retries.forEach(clearTimeout);
    };
  }, [pageNumber, pageWidth, paintHighlights]);

  useEffect(() => {
    if (bbox && scale > 0 && bboxRef.current) {
      onHighlightResult?.({ matched: true, target: bboxRef.current });
    }
  }, [bbox, onHighlightResult, scale]);

  return (
    <div ref={pageWrapRef} className="relative inline-block max-w-full">
      <Page
        pageNumber={pageNumber}
        width={pageWidth}
        renderTextLayer
        renderAnnotationLayer={false}
        onLoadSuccess={(page) => {
          setPdfPageWidth(page.originalWidth);
          onLoadSuccess(page);
        }}
        onRenderSuccess={onRenderSuccess}
        onRenderTextLayerSuccess={paintHighlights}
        loading={<PdfPagePlaceholder height={Math.round(pageWidth * DEFAULT_PAGE_RATIO)} />}
        error={
          <PdfPageError
            pageNumber={pageNumber}
            height={Math.round(pageWidth * DEFAULT_PAGE_RATIO)}
          />
        }
        className="max-w-full"
      />
      {bbox && scale > 0 && (
        <div
          ref={bboxRef}
          className="evidence-bbox-highlight pointer-events-none absolute"
          style={{
            left: Math.max(0, bbox.x0 * scale - bboxPaddingX),
            top: Math.max(0, bbox.y0 * scale - bboxPaddingY),
            width:
              Math.min(pageWidth, bbox.x1 * scale + bboxPaddingX) -
              Math.max(0, bbox.x0 * scale - bboxPaddingX),
            height: (bbox.y1 - bbox.y0) * scale + bboxPaddingY * 2,
          }}
        />
      )}
    </div>
  );
}

function PdfPagePlaceholder({ height }: { height: number }) {
  return (
    <div
      className="grid w-full place-items-center bg-white/95"
      style={{ height }}
      aria-hidden
    >
      <Spinner size={18} />
    </div>
  );
}

function PdfPageError({ pageNumber, height }: { pageNumber: number; height: number }) {
  return (
    <div
      className="grid w-full place-items-center bg-surface text-sm text-negative"
      style={{ height }}
    >
      Page {pageNumber} could not be rendered.
    </div>
  );
}
