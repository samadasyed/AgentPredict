#!/usr/bin/env python3
"""
Screenshot a URL after a REAL wait via Chrome DevTools Protocol.

Unlike `chromium --screenshot --virtual-time-budget=...` (which freezes the clock
before a WebSocket app finishes connecting), this navigates, waits real seconds so
the live data renders, then captures.

  python scripts/shoot.py <url> <out.png> <wait_seconds>
Needs chromium-browser + the `websockets` package.
"""
import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request

import websockets

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/shot.png"
WAIT = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
PORT = 9222


def chromium_bin() -> str:
    for b in ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable"):
        from shutil import which
        if which(b):
            return b
    raise SystemExit("no chromium found")


async def capture(ws_url: str) -> bytes:
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        counter = 0

        async def cmd(method, params=None):
            nonlocal counter
            counter += 1
            mid = counter
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg

        await cmd("Page.enable")
        await cmd("Page.navigate", {"url": URL})
        await asyncio.sleep(WAIT)  # real time → WS connects + replay renders
        res = await cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        return base64.b64decode(res["result"]["data"])


def main():
    proc = subprocess.Popen(
        [chromium_bin(), "--headless=new", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", f"--remote-debugging-port={PORT}",
         "--window-size=1440,1200", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        targets = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/json/list", timeout=1))
                if any(t.get("type") == "page" for t in targets):
                    break
            except Exception:
                time.sleep(0.25)
        page = next(t for t in targets if t.get("type") == "page")
        data = asyncio.run(capture(page["webSocketDebuggerUrl"]))
        with open(OUT, "wb") as f:
            f.write(data)
        print(f"wrote {OUT} ({len(data)} bytes)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
