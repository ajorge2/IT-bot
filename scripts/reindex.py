"""
Nightly re-index script — runs the full ingestion pipeline.
Schedule with cron, APScheduler, or your cloud scheduler.

Usage:
    python scripts/reindex.py               # incremental (append new vectors)
    python scripts/reindex.py --full        # full re-index (clears first)

Cron example (runs at 2:00 AM nightly):
    0 2 * * * cd /opt/itbot && python scripts/reindex.py >> logs/reindex.log 2>&1
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is in path when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("reindex")


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-index the IT knowledge base")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Perform a full re-index (drops existing vectors first)",
    )
    args = parser.parse_args()

    from app.ingestion.indexer import run_ingestion

    log.info("Starting re-index (full=%s)", args.full)
    result = run_ingestion(clear_first=args.full)
    log.info(
        "Re-index complete: %d documents, %d chunks",
        result["documents_loaded"],
        result["chunks_indexed"],
    )


if __name__ == "__main__":
    main()
