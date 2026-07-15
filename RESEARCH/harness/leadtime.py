"""
WS-vs-poll lead-time analyzer (B-003 decisive experiment, cycle-4 tooling).

Pairs the two capture streams:
- poll capture (polymarket_agent.jsonl): 5s midpoint samples per token
- WS capture (clob_ws.jsonl): CLOB market-channel messages; price_change
  entries carry per-asset best_bid/best_ask -> WS midpoint series

and answers, per token and in aggregate:
- lead time: when the poll detects a price change, how much earlier did the
  WS see midpoint movement for the same asset (within the same poll gap)?
- coverage: fraction of poll-detected changes preceded by WS movement
- ws_only: WS midpoint moves with NO poll-visible change in the following
  poll interval (order-book information polling never sees)
- reliability: connects/disconnects and the largest silent gap

  python RESEARCH/harness/leadtime.py [capture_dir]

Both streams are stamped with this machine's clock (poll timestamp_ms /
WS recv_ms), so lead times are same-clock and not skewed by server offsets.

Owner: Saify
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import load_capture  # noqa: E402

MID_EPS = 1e-9  # any best_bid/ask midpoint change counts as WS movement


@dataclass
class LeadStats:
    poll_changes: int
    covered: int              # poll changes with WS movement in the same gap
    leads_ms: list            # detect_ts - first WS movement ts, per covered change
    ws_moves: int
    ws_only: int              # WS moves with no poll change by the next sample


def _poll_series(cap) -> dict[str, list[tuple[int, float]]]:
    out: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for poll in cap.polls:
        for s in poll.get("snapshots", []):
            out[s["token_id"]].append((int(s["timestamp_ms"]), float(s["probability"])))
    for v in out.values():
        v.sort()
    return out


def _ws_mid_series(capture_dir: Path) -> tuple[dict[str, list[tuple[int, float]]], dict]:
    """Per-asset (recv_ms, midpoint) series + reliability info."""
    mids: dict[str, list[tuple[int, float]]] = defaultdict(list)
    rel = {"connects": 0, "disconnects": 0, "msgs": 0, "max_gap_ms": 0}
    last_recv = None
    for path in sorted(capture_dir.rglob("clob_ws.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            kind = rec.get("kind")
            if kind == "ws_connect":
                rel["connects"] += 1
            elif kind == "ws_disconnect":
                rel["disconnects"] += 1
            if kind != "ws_msg":
                continue
            rel["msgs"] += 1
            recv = int(rec["recv_ms"])
            if last_recv is not None:
                rel["max_gap_ms"] = max(rel["max_gap_ms"], recv - last_recv)
            last_recv = recv
            payload = rec.get("payload", {})
            if rec.get("event_type") == "price_change":
                for ch in payload.get("price_changes", []):
                    try:
                        mid = (float(ch["best_bid"]) + float(ch["best_ask"])) / 2
                    except (KeyError, TypeError, ValueError):
                        continue
                    mids[ch.get("asset_id", "")].append((recv, mid))
            elif rec.get("event_type") == "book":
                bids = payload.get("bids") or []
                asks = payload.get("asks") or []
                try:
                    bb = max(float(b["price"]) for b in bids)
                    ba = min(float(a["price"]) for a in asks)
                except (ValueError, KeyError, TypeError):
                    continue
                mids[payload.get("asset_id", "")].append((recv, (bb + ba) / 2))
    for v in mids.values():
        v.sort()
    return mids, rel


def _ws_movements(series: list[tuple[int, float]]) -> list[int]:
    """Timestamps where the WS midpoint actually changed."""
    return [t for (t, m), (_, prev) in zip(series[1:], series[:-1])
            if abs(m - prev) > MID_EPS]


def analyze(capture_dir: str | Path) -> tuple[dict[str, LeadStats], dict]:
    capture_dir = Path(capture_dir)
    cap = load_capture(capture_dir)
    polls = _poll_series(cap)
    mids, rel = _ws_mid_series(capture_dir)

    # Only compare inside the window where BOTH streams were recording —
    # poll changes from before the WS recorder started must not count
    # against WS coverage.
    all_recv = [t for series in mids.values() for t, _ in series]
    ws_start = min(all_recv) if all_recv else None
    ws_end = max(all_recv) if all_recv else None

    out: dict[str, LeadStats] = {}
    for token, ppath in polls.items():
        moves_ts = _ws_movements(mids.get(token, []))
        poll_changes = covered = 0
        leads: list[int] = []
        for (t_prev, p_prev), (t_now, p_now) in zip(ppath, ppath[1:]):
            if abs(p_now - p_prev) <= MID_EPS:
                continue
            if ws_start is None or t_prev < ws_start or t_now > ws_end:
                continue  # outside the paired window
            poll_changes += 1
            in_gap = [t for t in moves_ts if t_prev < t <= t_now]
            if in_gap:
                covered += 1
                leads.append(t_now - in_gap[0])
        # WS moves with no poll-visible change by the next poll sample
        ws_only = 0
        for t in moves_ts:
            nxt = next(((tt, pp) for tt, pp in ppath if tt >= t), None)
            prv = next(((tt, pp) for tt, pp in reversed(ppath) if tt < t), None)
            if nxt and prv and abs(nxt[1] - prv[1]) <= MID_EPS:
                ws_only += 1
        if poll_changes or moves_ts:
            out[token] = LeadStats(poll_changes, covered, leads, len(moves_ts), ws_only)
    return out, rel


def main() -> None:
    capture_dir = sys.argv[1] if len(sys.argv) > 1 else "research_capture"
    stats, rel = analyze(capture_dir)
    all_leads = sorted(l for s in stats.values() for l in s.leads_ms)
    poll_changes = sum(s.poll_changes for s in stats.values())
    covered = sum(s.covered for s in stats.values())
    ws_moves = sum(s.ws_moves for s in stats.values())
    ws_only = sum(s.ws_only for s in stats.values())

    print(f"tokens with activity: {len(stats)}")
    print(f"poll-detected changes: {poll_changes}  covered by WS: {covered}"
          f" ({covered / poll_changes:.0%})" if poll_changes else
          "poll-detected changes: 0")
    if all_leads:
        n = len(all_leads)
        print(f"WS lead over poll detection: p50={all_leads[n//2]/1000:.1f}s "
              f"p90={all_leads[int(n*0.9)]/1000:.1f}s max={all_leads[-1]/1000:.1f}s")
    print(f"WS midpoint moves: {ws_moves}  poll-invisible (ws_only): {ws_only}"
          + (f" ({ws_only / ws_moves:.0%})" if ws_moves else ""))
    print(f"WS reliability: connects={rel['connects']} disconnects={rel['disconnects']}"
          f" msgs={rel['msgs']} max_silent_gap={rel['max_gap_ms']/1000:.0f}s")


if __name__ == "__main__":
    main()
