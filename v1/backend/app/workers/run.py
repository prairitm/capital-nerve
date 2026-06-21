"""CLI entry point: `python -m app.workers.run`.

Drives `pipeline_worker.run_forever_sync()` from a process supervised by
docker, systemd, or your local terminal. The FastAPI process can run the same
loop in-process when `WORKER_INPROCESS=true` — this file exists for the
production split where API and workers run on separate machines.
"""
from __future__ import annotations

import logging

from app.workers.pipeline_worker import run_forever_sync


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    run_forever_sync()


if __name__ == "__main__":
    main()
