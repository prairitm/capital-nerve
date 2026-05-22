"""Background workers for CapitalNerve.

Currently exposes one worker: the pipeline worker, which polls
`extraction_jobs` for PENDING rows and runs each through the ingestion
pipeline. Designed to run either inside the FastAPI process (dev convenience,
controlled by `WORKER_INPROCESS`) or as a standalone CLI:

    python -m app.workers.run
"""
