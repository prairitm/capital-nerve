import { useMemo } from "react";
import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  GitBranch,
  Layers,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import type { LineageGraph, LineageNode, LineageNodeKind } from "@/api/types";
import { formatExtractionConfidence } from "@/lib/format";

interface Props {
  graph: LineageGraph;
  className?: string;
}

const LANE_ORDER: LineageNodeKind[] = [
  "extracted_value",
  "financial_fact",
  "calculated_metric",
  "generated_signal",
  "intelligence_card",
];

const LANE_LABEL: Record<LineageNodeKind, string> = {
  extracted_value: "Extracted values",
  financial_fact: "Facts",
  calculated_metric: "Metric",
  generated_signal: "Signal",
  intelligence_card: "Card",
};

const LANE_ICON: Record<LineageNodeKind, typeof FileText> = {
  extracted_value: FileText,
  financial_fact: Layers,
  calculated_metric: Sparkles,
  generated_signal: GitBranch,
  intelligence_card: CheckCircle2,
};

/**
 * Render the lineage payload returned by the reproducibility endpoint as a
 * five-lane horizontal flow:
 *
 *   Extracted → Facts → Metric → Signal → Card
 *
 * Nodes carry the data we care about for analyst trust (page numbers,
 * confidence, anomaly status). The component is deliberately read-only and
 * uses plain CSS columns — no graph layout library — so it composes with
 * the existing card styles and stays cheap to render on every IO page.
 */
export function ExtractionLineageGraph({ graph, className }: Props) {
  const lanes = useMemo(() => {
    const grouped: Record<LineageNodeKind, LineageNode[]> = {
      extracted_value: [],
      financial_fact: [],
      calculated_metric: [],
      generated_signal: [],
      intelligence_card: [],
    };
    for (const node of graph.nodes) {
      grouped[node.kind]?.push(node);
    }
    return grouped;
  }, [graph]);

  const hasAny = graph.nodes.length > 0;
  if (!hasAny) return null;

  return (
    <section
      className={clsx(
        "card overflow-hidden",
        className,
      )}
      aria-label="Extraction lineage graph"
    >
      <header className="flex items-baseline justify-between gap-3 px-5 py-4 border-b border-line/60">
        <div>
          <h2 className="text-base font-semibold">Extraction lineage</h2>
          <p className="text-xs text-ink-mute mt-0.5">
            From the source filing line to the published card.
          </p>
        </div>
        <span className="text-[11px] uppercase tracking-wider text-ink-mute">
          {graph.nodes.length} nodes
        </span>
      </header>
      <div className="grid gap-3 px-5 py-4 lg:grid-cols-5 md:grid-cols-3 grid-cols-1">
        {LANE_ORDER.map((kind) => {
          const items = lanes[kind];
          const Icon = LANE_ICON[kind];
          return (
            <div key={kind} className="space-y-2">
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-ink-mute">
                <Icon size={12} aria-hidden />
                {LANE_LABEL[kind]}
              </div>
              {items.length === 0 ? (
                <div className="text-[11px] text-ink-mute italic">none</div>
              ) : (
                items.map((node) => <LineageCard key={node.id} node={node} />)
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LineageCard({ node }: { node: LineageNode }) {
  const validation = node.validation_status;
  const tone =
    validation === "anomaly"
      ? "border-mixed/40 bg-mixed-bg/30"
      : validation === "quarantined"
        ? "border-negative/40 bg-negative-bg/30"
        : "border-line/40 bg-surface-2/30";

  return (
    <div className={clsx("rounded-md border px-2.5 py-2 space-y-1", tone)}>
      <div className="text-xs font-medium text-ink line-clamp-2" title={node.label}>
        {node.label}
      </div>
      {node.detail && (
        <div className="text-[11px] text-ink-soft line-clamp-2" title={node.detail}>
          {node.detail}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-ink-mute">
        {node.page_number != null && <span>p.{node.page_number}</span>}
        {node.confidence_score != null && (
          <span title="Extraction confidence (0–100)">
            {formatExtractionConfidence(node.confidence_score)} conf
          </span>
        )}
        {validation === "anomaly" && (
          <span className="inline-flex items-center gap-0.5 text-mixed">
            <AlertTriangle size={10} aria-hidden /> anomaly
          </span>
        )}
        {validation === "quarantined" && (
          <span className="inline-flex items-center gap-0.5 text-negative">
            <ShieldAlert size={10} aria-hidden /> quarantined
          </span>
        )}
      </div>
    </div>
  );
}
