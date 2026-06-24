from __future__ import annotations

import argparse
import logging
import os

from derlem_worker.config import load_config
from derlem_worker.jobs import Worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Derlem background worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--worker-id", help="Stable worker identifier")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker = Worker(load_config(), worker_id=args.worker_id)
    if args.once:
        worker.run_once()
        return
    worker.run_forever()


if __name__ == "__main__":
    main()
