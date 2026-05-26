import { useState } from "react";
import clsx from "clsx";
import { Download } from "lucide-react";
import { api } from "@/api/client";
import type { ReproducibilityBundle } from "@/api/types";

interface Props {
  objectId: number;
  className?: string;
}

/**
 * Download the analyst-reproducibility bundle for an intelligence object.
 *
 * One click, one JSON file: signal rule, metric formula, resolved inputs,
 * source quotes, pipeline versions, and the lineage graph — enough for an
 * analyst (or another model) to replay the verdict offline.
 */
export function ReproducibilityExportButton({ objectId, className }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      const bundle = await api<ReproducibilityBundle>(
        `/v1/intelligence-objects/${objectId}/reproducibility`,
      );
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `intelligence-object-${objectId}-reproducibility.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={clsx("inline-flex flex-col items-end gap-1", className)}>
      <button
        type="button"
        onClick={handleClick}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-md border border-line/60 bg-surface-2/40 px-2.5 py-1 text-xs font-medium text-ink hover:bg-surface-2 disabled:opacity-60"
        title="Download analyst-reproducibility bundle (JSON)"
      >
        <Download size={12} aria-hidden />
        {busy ? "Exporting…" : "Export bundle"}
      </button>
      {error && <span className="text-[11px] text-negative">{error}</span>}
    </div>
  );
}
