"""
CLI report over a flight-recorder capture dir (B-002 eval harness v0).

  python RESEARCH/harness/report.py [capture_dir]      # default: research_capture

Prints capture volume, grounding scores (with ungrounded claims per cycle),
PASS/FAIL separation, latency percentiles, and outcome-consistency counts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import evaluate, load_capture  # noqa: E402


def main() -> None:
    capture_dir = sys.argv[1] if len(sys.argv) > 1 else "research_capture"
    if not Path(capture_dir).exists():
        sys.exit(f"no capture dir at {capture_dir!r} — run with RESEARCH_CAPTURE=1 first")
    report = evaluate(load_capture(capture_dir))

    fmt = lambda v: "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else v)
    print(f"capture: {capture_dir}")
    print(f"  polls={report['n_polls']}  markets={report['n_markets']}  "
          f"ticks held/emitted={report['ticks_held']}/{report['ticks_emitted']}")
    print(f"  cycles={report['n_cycles']}  skips={report['n_skips']}  errors={report['n_errors']}")
    print(f"grounding: pass-mean={fmt(report['grounding_mean_pass'])}  "
          f"fail-mean={fmt(report['grounding_mean_fail'])}  "
          f"separation={fmt(report['separation'])}")
    print(f"latency_ms: p50={fmt(report['latency_ms_p50'])}  p95={fmt(report['latency_ms_p95'])}")
    print(f"outcomes after explanation: {report['outcomes'] or 'n/a'}")
    for r in report["cycles"]:
        flag = "PASS" if r["passed"] else "FAIL"
        print(f"  [{flag}] {r['trigger_key']}  grounding={fmt(r['grounding'])}  "
              f"latency={fmt(r['latency_ms'])}ms  outcome={r['outcome']}"
              + (f"  ungrounded={r['ungrounded_claims']}" if r["ungrounded_claims"] else ""))


if __name__ == "__main__":
    main()
