"""
Flight recorder — append-only JSONL capture of the data that otherwise
evaporates (sub-threshold price ticks, RAG cycle inputs/outputs, skipped
triggers). Research bet B-001 (RESEARCH/BETS.md).

Off by default. Enable with RESEARCH_CAPTURE=1; files land in
RESEARCH_CAPTURE_DIR (default ./research_capture, gitignored) as
<dir>/<YYYYMMDD>/<component>.jsonl, one JSON object per line.

Best-effort by design: a capture failure must never break the serving path —
every write error is swallowed (warned once per recorder).

Owner: Saify
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_ENABLED = "RESEARCH_CAPTURE"
_ENV_DIR = "RESEARCH_CAPTURE_DIR"
_DEFAULT_DIR = "research_capture"


class FlightRecorder:
    """Thread-safe, env-gated JSONL appender for one component's capture stream."""

    def __init__(self, component: str) -> None:
        self._component = component
        self.enabled: bool = os.getenv(_ENV_ENABLED, "0") == "1"
        self._base_dir = Path(os.getenv(_ENV_DIR, _DEFAULT_DIR))
        self._lock = threading.Lock()
        self._warned = False
        if self.enabled:
            logger.info("[flight-recorder] %s capturing to %s", component, self._base_dir)

    def record(self, kind: str, payload: dict) -> None:
        """Append one record. No-op when disabled; never raises."""
        if not self.enabled:
            return
        try:
            now_ms = int(time.time() * 1000)
            day = time.strftime("%Y%m%d", time.gmtime(now_ms / 1000))
            path = self._base_dir / day / f"{self._component}.jsonl"
            line = json.dumps({"ts_ms": now_ms, "kind": kind, **payload}, default=str)
            with self._lock:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception as exc:
            if not self._warned:
                logger.warning("[flight-recorder] %s write failed (%s) — capture is "
                               "best-effort, serving path unaffected", self._component, exc)
                self._warned = True
