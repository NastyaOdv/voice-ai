import asyncio
import sys

from app.worker import run_worker

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


if __name__ == "__main__":
    asyncio.run(run_worker())
