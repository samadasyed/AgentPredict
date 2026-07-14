"""
Standalone pre-fight capture runner (B-001). Runs the REAL Polymarket agent
with a null emitter — no engine, no gateway, no RAG, no API keys needed —
so the flight recorder collects live price paths days before fight night,
independent of the containerized stack (whose captures don't persist until
the volume-mount proposal lands).

  python RESEARCH/harness/capture_run.py            # capture to ./research_capture
  RESEARCH_CAPTURE_DIR=/somewhere python RESEARCH/harness/capture_run.py

Stop with Ctrl-C (or kill the pid). Polls at POLYMARKET_POLL_INTERVAL_S
(default 5s) — identical API load to the production agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Capture is the entire point of this runner — force it on before the agent
# module reads its env at import time.
os.environ["RESEARCH_CAPTURE"] = "1"
os.environ.setdefault("RESEARCH_CAPTURE_DIR", "research_capture")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.polymarket.agent import PolymarketAgent  # noqa: E402
from agents.polymarket.client import PolymarketClient  # noqa: E402


class NullEmitter:
    """Stands in for the engine gRPC emitter — accepts and discards."""

    def emit(self, event) -> bool:
        return True

    def close(self) -> None:
        pass


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    agent = PolymarketAgent(client=PolymarketClient(), emitter=NullEmitter())
    try:
        await agent.run()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
