"""RQ worker entrypoint. Run with: python worker.py"""

import logging
import os

from redis import Redis
from rq import Worker, Queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

redis_conn = Redis.from_url(REDIS_URL)
queue = Queue(connection=redis_conn)

if __name__ == "__main__":
    worker = Worker([queue], connection=redis_conn)
    worker.work(with_scheduler=False)
