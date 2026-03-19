"""Worker entrypoint for cloud deployments.

Run this as a separate service (Render Worker / Railway) to keep the pipeline
running 24/7.
"""

from __future__ import annotations

import asyncio
import logging

from scheduler import scheduler_loop


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(scheduler_loop())


if __name__ == "__main__":
    main()
