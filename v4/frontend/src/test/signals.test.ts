import { describe, expect, it } from "vitest";
import type { MetricValue } from "@/api/types";
import {
  buildStructuredRuleText,
  buildStructuredTriggerNarrative,
} from "@/lib/signals";

const metric: MetricValue = {
  metric_code: "cfo_to_pat",
  metric_name: "CFO To PAT",
  metric_value: 1.7,
  unit: "x",
  category: "cash_quality",
  period_start: null,
  period_end: "2025-09-30",
  calculation_data: {},
};

describe("structured signal rules", () => {
  it("formats a threshold rule with the metric unit", () => {
    expect(
      buildStructuredRuleText(
        { metric_key: "cfo_to_pat", op: ">=", value: 1 },
        [metric],
      ),
    ).toBe("CFO To PAT >= 1.00x");
  });

  it("explains the observed value that satisfied a rule", () => {
    expect(
      buildStructuredTriggerNarrative(
        { metric_key: "cfo_to_pat", op: ">=", value: 1 },
        [metric],
      ),
    ).toBe("CFO To PAT was 1.70x, which met or exceeded the trigger of 1.00x.");
  });

  it("joins alternative catalog conditions", () => {
    expect(
      buildStructuredRuleText({
        any: [
          { metric_key: "reconciliation_gap", op: ">", value: 2 },
          { metric_key: "reconciliation_gap", op: "<", value: -2 },
        ],
      }),
    ).toBe("Reconciliation Gap > 2.00 or Reconciliation Gap < -2.00");
  });
});
