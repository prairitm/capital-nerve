# Development error taxonomy

The aggregate before-fix report contains the original 150-fact checkpoint plus all new draft facts. It scored 83.16% provisional published precision, 67.76% coverage, and 57.71% recall, with 43 incorrect labeled publications and seven spurious newspaper publications. After the fixes it scores 100% provisional published precision, 61.21% coverage/recall, a 19.39% review rate, a 19.39% abstention rate, zero spurious publications, and zero page, period, period-type, basis, unit, evidence, or unresolved-conflict publication errors.

| Failure class | Baseline evidence | General treatment | After fix |
| --- | --- | --- | --- |
| Document discovery | Infosys April `nse_auto` rejected all discovered candidates | Preserve document queue and use supported manual URL fallback | Fallback reached ingestion; discovery failure remains reported |
| Processing timeout | 380-page scanned Infosys outcome exceeded 900 seconds | Missing parsed artifacts become explicit abstentions | 40 safe abstentions; no crash/publication |
| PDF text layer / OCR | UltraTech, Asian Paints, HUL, Bharti, Infosys annual | Keep page evidence mandatory; publish deterministic rows only, otherwise review/abstain | No OCR-derived incorrect publication |
| Page-number loss | Real LLM fallback observations frequently lacked `source_page` | Review reconciliation rejects evidence-incomplete approvals | Zero invalid pages published; actual HUL approval blocked |
| Table detection / merged particulars | Asian Paints serial-number plus particulars columns | Use the rightmost textual label before the selected value column | Wrong tax subtotal removed |
| Prior-period value mistaken for label | Annual, half-year, and nine-month selections place earlier numeric columns before the target | Require alphabetic content when choosing the rightmost particulars cell | Cumulative-period rows recovered without relaxing evidence |
| Vision/OCR digit corruption and dropped basis heading | Recoverable L&T caches contained internally plausible but visually wrong digits; repeated same-basis revenue anchors materially disagreed across pages | Treat material cross-page statement disagreement as an unresolved document conflict and route every candidate to review | 29 wrong publications reduced to zero; 43 L&T facts withheld |
| Incorrect basis | Tata Steel used “Statement of Profit and Loss” rather than “Financial Results” | Recognize basis around both statement-title forms | Zero wrong basis |
| Incorrect period / period type | Quarter and year columns share 31 March in Infosys and ITC | Require explicit section match; ambiguous columns abstain | Zero period or period-type errors |
| Unit normalization | Maruti and Dr Reddy report INR millions | Normalize million/lakh/thousand to crore, never scale EPS, retain exact conversion evidence | Zero wrong units/values |
| Evidence rounding | Sun Pharma normalized evidence rounded 14315.86 to 14315.9 | Preserve the exact normalized decimal in evidence | Zero unsupported evidence |
| Accounting negative | Parentheses occur across tax, inventory, and OCI rows | Existing signed-number parsing retained and regression-covered | No sign errors observed |
| Row alias mapping | Tata “Net Profit / (Loss) for the period” and spelled-out EPS | Add general slash-loss PAT and basic/diluted earnings-per-share aliases | Correct rows publish |
| Ratio mistaken for amount | Tata net-profit-margin rows overwrote PAT | Exclude margin/ratio/turnover rows from core amount mapping | Zero wrong PAT/page |
| NCI attribution | Sun Pharma owners-after-NCI row overwrote total group PAT | Prefer group PAT before non-controlling attribution | Correct consolidated PAT |
| Multiple tax scopes | ITC has separate continuing and discontinued tax rows but no operation dimension | Withhold core tax across table/page continuations | Safe abstention, documented contract gap |
| Multi-issuer document | Sun Pharma newspaper contains other issuers' complete tables | Detect issuer-mixed newspaper pages and skip automatic extraction | Seven spurious publications reduced to zero |
| Missing evidence | Genuine review candidates lacked page attribution | Keep facts out of `extracted_values`, metrics, and signals | Zero evidence-incomplete publications |

The remaining failure classes are coverage-only: the 380-page timeout, HUL's weak table layer, partial OCR recovery on UltraTech, conservative annual-column selection, and the unsupported continuing/discontinued tax dimension. They are intentionally represented as abstentions rather than precision failures.
