import { afterEach, describe, expect, it, vi } from "vitest";
import { applyPdfPageHighlights, buildEvidenceHighlights } from "@/lib/pdfHighlight";

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("PDF evidence highlighting", () => {
  it("returns the matched target without scrolling the browser window", () => {
    const windowScroll = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    const textLayer = document.createElement("div");
    const span = document.createElement("span");
    span.setAttribute("role", "presentation");
    span.textContent = "Revenue from operations";
    textLayer.appendChild(span);
    document.body.appendChild(textLayer);

    const result = applyPdfPageHighlights(
      textLayer,
      buildEvidenceHighlights(["Revenue from operations"]),
    );

    expect(result).toEqual({ matched: true, target: span });
    expect(span).toHaveClass("evidence-highlight");
    expect(windowScroll).not.toHaveBeenCalled();
  });

  it("reports a clean miss when the PDF text layer has no evidence text", () => {
    const textLayer = document.createElement("div");
    const span = document.createElement("span");
    span.setAttribute("role", "presentation");
    span.textContent = "Unrelated filing text";
    textLayer.appendChild(span);

    expect(
      applyPdfPageHighlights(
        textLayer,
        buildEvidenceHighlights(["Profit after tax"]),
      ),
    ).toEqual({ matched: false, target: null });
  });
});
