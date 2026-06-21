#!/usr/bin/env python3
"""
Terminal viewer for the AgentPredict gateway — watch both live streams without a
browser. Useful on headless servers.

  python scripts/watch-stream.py                      # ws://localhost:8000/ws
  python scripts/watch-stream.py ws://host:8000/ws    # custom URL
  python scripts/watch-stream.py ws://localhost:8000/ws 20   # run 20s then exit

Needs the `websockets` package (in .venv-test, or `pip install websockets`).
Or run with no host deps via:  make watch
"""
import asyncio
import json
import sys

import websockets

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws"
RUN_SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else None

C_DIM = "\033[2m"; C_GRN = "\033[32m"; C_CYN = "\033[36m"; C_YEL = "\033[33m"; C_RST = "\033[0m"


def fmt_event(d):
    if "market_event" in d:
        m = d["market_event"]
        arrow = "▲" if m.get("delta", 0) >= 0 else "▼"
        return (f"{C_GRN}MARKET{C_RST}  {m['outcome'][:42]:42}  "
                f"p={m['probability']:.3f} {arrow}{abs(m.get('delta',0)):.3f}")
    if "fight_event" in d:
        f = d["fight_event"]
        return (f"{C_CYN}FIGHT {C_RST}  {f['fighter_name'][:24]:24}  "
                f"{f['stat_type']}={f.get('value')} r{f.get('round')}")
    return f"event {d.get('event_id','')[:8]}"


async def main():
    n_ev = n_pred = 0
    print(f"{C_DIM}connecting to {URL} …{C_RST}")
    async with websockets.connect(URL) as ws:
        print(f"{C_DIM}connected — Ctrl+C to quit{C_RST}\n")
        loop = asyncio.get_event_loop()
        start = loop.time()
        while True:
            timeout = None
            if RUN_SECONDS is not None:
                remaining = RUN_SECONDS - (loop.time() - start)
                if remaining <= 0:
                    break
                timeout = remaining
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            d = msg.get("data", {})
            if msg.get("type") == "event":
                n_ev += 1
                print(fmt_event(d))
            elif msg.get("type") == "prediction":
                n_pred += 1
                conf = d.get("confidence", 0)
                print(f"{C_YEL}PREDICT{C_RST} conf={conf:.2f}  {d.get('explanation','')[:80]}")
    print(f"\n{C_DIM}summary: {n_ev} events, {n_pred} predictions{C_RST}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye")
