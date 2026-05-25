import clsx from "clsx";
import { TrendingDown, TrendingUp, AlertTriangle, Minus } from "lucide-react";
import type { AnalystSummary, AnalystSummaryTone } from "@/api/types";

interface Props {
  summary: AnalystSummary | null | undefined;
  className?: string;
}

const TONE_TEXT: Record<AnalystSummaryTone, string> = {
  positive: "text-positive",
  negative: "text-negative",
  mixed: "text-mixed",
  neutral: "text-neutral",
};

const TONE_CHIP: Record<AnalystSummaryTone, string> = {
  positive: "chip-positive",
  negative: "chip-negative",
  mixed: "chip-mixed",
  neutral: "chip-neutral",
};

const VERDICT_LABEL: Record<AnalystSummaryTone, string> = {
  positive: "Constructive quarter",
  negative: "Challenging quarter",
  mixed: "Mixed quarter",
  neutral: "Steady quarter",
};

function ToneIcon({ tone }: { tone: AnalystSummaryTone }) {
  switch (tone) {
    case "positive":
      return <TrendingUp size={14} aria-hidden />;
    case "negative":
      return <TrendingDown size={14} aria-hidden />;
    case "mixed":
      return <AlertTriangle size={14} aria-hidden />;
    default:
      return <Minus size={14} aria-hidden />;
  }
}

/**
 * Themed analyst summary pinned at the top of the event detail page.
 *
 * The verdict + per-theme tones come straight from the backend payload
 * persisted alongside `intelligence_cards.calculations_json["analyst_summary"]`
 * — see `services/event_summary.build_analyst_summary`. Renders nothing if
 * the event has neither cards nor fired signals.
 */
export function AnalystSummaryCard({ summary, className }: Props) {
  if (!summary || summary.themes.length === 0) return null;

  return (
    <section
      className={clsx("card p-5 md:p-6 space-y-4", className)}
      aria-label="Analyst summary"
    >
      <header className="flex items-baseline justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-ink-soft">
            Analyst summary
          </div>
          <h2 className="text-base font-semibold mt-0.5">
            {VERDICT_LABEL[summary.verdict] ?? "Quarter summary"}
          </h2>
        </div>
        <span className={clsx(TONE_CHIP[summary.verdict], "shrink-0 capitalize")}>
          <ToneIcon tone={summary.verdict} /> {summary.verdict}
        </span>
      </header>

      <ol className="space-y-3">
        {summary.themes.map((theme) => (
          <li
            key={theme.label}
            className="card-2 p-3.5 flex items-start gap-3"
          >
            <div className={clsx("shrink-0 mt-0.5", TONE_TEXT[theme.tone])}>
              <ToneIcon tone={theme.tone} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">{theme.label}</h3>
                <span
                  className={clsx(
                    "text-[11px] uppercase tracking-wider capitalize",
                    TONE_TEXT[theme.tone],
                  )}
                >
                  {theme.tone}
                </span>
              </div>
              <p className="text-sm text-ink-mute leading-relaxed mt-1">
                {theme.sentence}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
