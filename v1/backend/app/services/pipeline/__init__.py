"""Real ingestion pipeline.

Owns the stages that turn an uploaded source document into the canonical
`extracted_values -> financial_statement_facts -> calculated_metrics ->
generated_signals -> intelligence_cards -> card_evidence` chain that every
read-side surface (cards API, /v1 intelligence objects, drawer, retail summary,
etc.) consumes.

Each stage is its own module so a future pipeline can swap the LLM, the rule
engine, or the storage backend without rewriting the orchestrator. The runner
in `runner.py` is the only place that wires them together.
"""

from app.services.pipeline.runner import run_pipeline_for_document

__all__ = ["run_pipeline_for_document"]
