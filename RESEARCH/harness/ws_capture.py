"""
CLOB websocket side-recorder (B-003 decisive experiment).

Subscribes to Polymarket's public market websocket for every token the poll
capture is tracking and records raw messages via the flight recorder
(component "clob_ws"), so fight night yields a paired WS-vs-poll dataset.

  python RESEARCH/harness/ws_capture.py     # capture to ./research_capture

Token discovery: reads the newest poll record in the capture dir (the poll
runner is the source of truth for which markets matter) and re-checks every
TOKEN_REFRESH_S, reconnecting when the set changes. Auto-reconnects with
backoff on any error; connection lifecycle events are recorded too, so gaps
are measurable — WS reliability is itself part of the experiment.

Needs the `websockets` package. Stop with Ctrl-C / pkill -f ws_capture.

Owner: Saify
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ["RESEARCH_CAPTURE"] = "1"
os.environ.setdefault("RESEARCH_CAPTURE_DIR", "research_capture")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import websockets  # noqa: E402

from agents.shared.flight_recorder import FlightRecorder  # noqa: E402

logger = logging.getLogger("ws_capture")

WS_URL = os.getenv("CLOB_WS_URL",
                   "wss://ws-subscriptions-clob.polymarket.com/ws/market")
TOKEN_REFRESH_S = 600
RECONNECT_MIN_S, RECONNECT_MAX_S = 2, 60


def discover_tokens(capture_dir: Path) -> tuple[list[str], dict[str, str]]:
    """Token ids (+ token->title map) from the newest poll record on disk."""
    files = sorted(capture_dir.rglob("polymarket_agent.jsonl"))
    for f in reversed(files):
        for line in reversed(f.read_text(encoding="utf-8").splitlines()):
            rec = json.loads(line)
            if rec.get("kind") == "poll":
                snaps = rec.get("snapshots", [])
                return ([s["token_id"] for s in snaps],
                        {s["token_id"]: s.get("title", "") for s in snaps})
    return [], {}


async def run() -> None:
    recorder = FlightRecorder("clob_ws")
    capture_dir = Path(os.environ["RESEARCH_CAPTURE_DIR"])
    backoff = RECONNECT_MIN_S

    while True:
        tokens, titles = discover_tokens(capture_dir)
        if not tokens:
            logger.warning("no tokens in poll capture yet — retrying in 30s")
            await asyncio.sleep(30)
            continue

        refreshed_at = time.monotonic()
        try:
            async with websockets.connect(WS_URL, open_timeout=15) as ws:
                await ws.send(json.dumps({"assets_ids": tokens, "type": "market"}))
                recorder.record("ws_connect", {"n_tokens": len(tokens)})
                logger.info("subscribed to %d tokens", len(tokens))
                backoff = RECONNECT_MIN_S

                while True:
                    if time.monotonic() - refreshed_at >= TOKEN_REFRESH_S:
                        new_tokens, _ = discover_tokens(capture_dir)
                        if new_tokens and set(new_tokens) != set(tokens):
                            logger.info("token set changed (%d -> %d) — resubscribing",
                                        len(tokens), len(new_tokens))
                            break  # reconnect with the new set
                        refreshed_at = time.monotonic()

                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    recv_ms = int(time.time() * 1000)
                    msgs = json.loads(raw)
                    for m in (msgs if isinstance(msgs, list) else [msgs]):
                        asset = m.get("asset_id", "")
                        recorder.record("ws_msg", {
                            "recv_ms": recv_ms,
                            "event_type": m.get("event_type"),
                            "asset_id": asset,
                            "title": titles.get(asset, ""),
                            "payload": m,
                        })
        except asyncio.TimeoutError:
            # 60s of silence on live markets — treat as a stale socket.
            recorder.record("ws_disconnect", {"reason": "recv_timeout"})
            logger.warning("recv timeout — reconnecting")
        except Exception as exc:
            recorder.record("ws_disconnect", {"reason": repr(exc)})
            logger.warning("ws error: %r — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_S)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
