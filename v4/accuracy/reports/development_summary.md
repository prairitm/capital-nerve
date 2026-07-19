# Expanded development benchmark summary

| Measure | Result |
| --- | ---: |
| Pipeline documents | 20 |
| Positive-label documents | 19 |
| Companies | 14 |
| Draft gold facts | 428 |
| Difficult PDFs | 14 |
| Maximum documents per company | 2 |
| Provisional published precision | 100.00% |
| Coverage | 61.21% |
| Recall | 61.21% |
| Review rate in deterministic replay | 19.39% |
| Abstention rate | 19.39% |
| Spurious published facts | 0 |
| Wrong evidence pages | 0 |
| Wrong periods / period types | 0 / 0 |
| Wrong bases / units | 0 / 0 |
| Unresolved conflicts published | 0 |
| Label approval status | 428 draft, 0 approved |

The result is **100% provisional published precision**, not “100% accuracy.” The replay publishes 262 facts, routes 83 to review, and abstains on 83. Coverage and recall are 61.21%, and release gates remain blocked because every gold label still requires independent human approval and the holdout has not been independently materialized or labeled.

The locked holdout manifest contains ten reserved companies/layouts and no routine results. The explicit release evaluator refuses to run until all ten immutable document IDs exist and all holdout labels are approved.
