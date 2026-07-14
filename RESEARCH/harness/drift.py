"""
Price-path drift analyzer over flight-recorder captures (cycle-4 tooling).

Answers, per market and in aggregate:
- how much the price actually moved at 5s resolution (range, total variation,
  max cumulative drift from any local reference)
- what fraction of movement lives below the product's emit threshold
- what-if emit counts at alternative thresholds (per-tick AND cumulative,
  mirroring the agent's DELTA_THRESHOLD and the orchestrator's
  cumulative-drift gate with its explanation-reset semantics)

  python RESEARCH/harness/drift.py [capture_dir] [--csv out.csv]

Stdlib only; offline; read-only over captures.

Owner: Saify
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import Capture, load_capture  # noqa: E402

THRESHOLDS = (0.002, 0.005, 0.01, 0.02)


@dataclass
class MarketDrift:
    market_id: str
    title: str
    n_ticks: int
    span_min: float          # capture duration covered, minutes
    p_first: float
    p_last: float
    p_min: float
    p_max: float
    total_variation: float   # sum of |tick-to-tick| moves
    max_tick: float          # largest single tick |move|
    max_cum_drift: float     # largest |p - ref| excursion from any local ref
    tick_emits: dict         # threshold -> would-emit count (per-tick gate)
    cum_emits: dict          # threshold -> trigger count (cumulative gate)


def _cum_triggers(probs: list[float], threshold: float) -> int:
    """Simulate the orchestrator's cumulative gate: ref starts at first price,
    a trigger fires when |p - ref| >= threshold and resets ref to p."""
    if not probs:
        return 0
    ref, n = probs[0], 0
    for p in probs[1:]:
        if abs(p - ref) >= threshold:
            n += 1
            ref = p
    return n


def _max_excursion(probs: list[float]) -> float:
    """Largest |move| between any point and a later point (max drawup/drawdown)."""
    best = 0.0
    lo = hi = probs[0] if probs else 0.0
    for p in probs:
        best = max(best, abs(p - lo), abs(p - hi))
        lo, hi = min(lo, p), max(hi, p)
    return best


def analyze(cap: Capture) -> list[MarketDrift]:
    # market_id -> (title, [(ts, prob)])
    paths: dict[str, tuple[str, list[tuple[int, float]]]] = {}
    for poll in cap.polls:
        for s in poll.get("snapshots", []):
            mid = s.get("market_id", "")
            title = s.get("title") or mid
            paths.setdefault(mid, (title, []))[1].append(
                (int(s["timestamp_ms"]), float(s["probability"])))

    out = []
    for mid, (title, pts) in paths.items():
        pts.sort()
        probs = [p for _, p in pts]
        if len(probs) < 2:
            continue
        moves = [abs(b - a) for a, b in zip(probs, probs[1:])]
        out.append(MarketDrift(
            market_id=mid, title=title, n_ticks=len(probs),
            span_min=(pts[-1][0] - pts[0][0]) / 60_000,
            p_first=probs[0], p_last=probs[-1],
            p_min=min(probs), p_max=max(probs),
            total_variation=sum(moves), max_tick=max(moves),
            max_cum_drift=_max_excursion(probs),
            tick_emits={t: sum(1 for m in moves if m >= t) for t in THRESHOLDS},
            cum_emits={t: _cum_triggers(probs, t) for t in THRESHOLDS},
        ))
    out.sort(key=lambda d: d.total_variation, reverse=True)
    return out


def print_report(drifts: list[MarketDrift]) -> None:
    if not drifts:
        print("no market price paths in capture")
        return
    span = max(d.span_min for d in drifts)
    print(f"markets={len(drifts)}  window≈{span:.0f} min  "
          f"ticks/market≈{sum(d.n_ticks for d in drifts)//len(drifts)}")
    hdr = f"{'market':38} {'p_last':>6} {'range':>6} {'totvar':>7} {'maxcum':>6}"
    hdr += "".join(f" {'e@' + str(t):>7}" for t in THRESHOLDS)
    print(hdr)
    for d in drifts:
        row = (f"{d.title[:38]:38} {d.p_last:6.3f} {d.p_max - d.p_min:6.3f} "
               f"{d.total_variation:7.3f} {d.max_cum_drift:6.3f}")
        row += "".join(f" {d.tick_emits[t]:3}/{d.cum_emits[t]:<3}" for t in THRESHOLDS)
        print(row)
    print("\ne@T columns = per-tick emits / cumulative triggers at threshold T")
    for t in THRESHOLDS:
        tick_total = sum(d.tick_emits[t] for d in drifts)
        cum_total = sum(d.cum_emits[t] for d in drifts)
        print(f"  threshold {t}: {tick_total} per-tick emits, {cum_total} cumulative triggers")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    capture_dir = args[0] if args else "research_capture"
    if not Path(capture_dir).exists():
        sys.exit(f"no capture dir at {capture_dir!r}")
    drifts = analyze(load_capture(capture_dir))
    print_report(drifts)
    if "--csv" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--csv") + 1])
        cols = ["market_id", "title", "n_ticks", "span_min", "p_first", "p_last",
                "p_min", "p_max", "total_variation", "max_tick", "max_cum_drift"]
        lines = [",".join(cols + [f"tick_e{t}" for t in THRESHOLDS]
                          + [f"cum_e{t}" for t in THRESHOLDS])]
        for d in drifts:
            vals = [str(getattr(d, c)).replace(",", ";") for c in cols]
            vals += [str(d.tick_emits[t]) for t in THRESHOLDS]
            vals += [str(d.cum_emits[t]) for t in THRESHOLDS]
            lines.append(",".join(vals))
        out.write_text("\n".join(lines) + "\n")
        print(f"csv written: {out}")


if __name__ == "__main__":
    main()
