"""
Explanation-quality eval harness v0 (research bet B-002, RESEARCH/BETS.md).

Reads flight-recorder captures (B-001 JSONL) and computes, per RAG cycle:

- grounding: fraction of the explanation's checkable claims (proper-noun
  phrases + numbers) traceable to the trigger, context window, or retrieved
  evidence. Ungrounded claims are the hallucination surface.
- timeliness: pipeline latency (latency_ms) and end-to-end tick→explanation
  time derived from the trigger timestamp.
- outcome consistency (feature, not verdict): from the captured price path,
  whether the market continued, reverted, or stayed flat in the window after
  the explanation.

Also computes the B-002 kill-criterion check: do verifier PASS and FAIL
populations separate on grounding score?

Stdlib only; runs fully offline. Not part of the serving path.

Owner: Saify
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Capitalized tokens that don't count as claims (sentence starters, filler,
# domain words every explanation contains). Mirrors the verifier's philosophy.
_STOP_CAPS = {
    "The", "This", "That", "These", "Those", "A", "An", "It", "Its", "In", "On",
    "At", "As", "After", "Before", "With", "Without", "However", "While",
    "Given", "Based", "Because", "Since", "There", "Their", "His", "Her",
    "If", "For", "But", "And", "Or", "No", "Not", "Odds", "Market", "Markets",
    "UFC", "MMA", "Round", "Fight", "Fighter", "Insufficient",
}

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z'’.-]+(?:\s+[A-Z][a-zA-Z'’.-]+)*")


# ─── Loading ──────────────────────────────────────────────────────────────────

@dataclass
class Capture:
    polls: list[dict] = field(default_factory=list)        # polymarket_agent "poll"
    cycles: list[dict] = field(default_factory=list)       # rag "cycle"
    skips: list[dict] = field(default_factory=list)        # rag "skip"
    errors: list[dict] = field(default_factory=list)       # rag "cycle_error"

    def price_path(self, market_id: str) -> list[tuple[int, float]]:
        """(timestamp_ms, probability) for one market, oldest first, from polls."""
        pts = []
        for poll in self.polls:
            for snap in poll.get("snapshots", []):
                if snap.get("market_id") == market_id:
                    pts.append((int(snap["timestamp_ms"]), float(snap["probability"])))
        pts.sort()
        return pts


def load_capture(capture_dir: str | Path) -> Capture:
    """Load every JSONL under a capture dir (searches day subdirs)."""
    cap = Capture()
    buckets = {"poll": cap.polls, "cycle": cap.cycles,
               "skip": cap.skips, "cycle_error": cap.errors}
    for path in sorted(Path(capture_dir).rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            bucket = buckets.get(rec.get("kind"))
            if bucket is not None:
                bucket.append(rec)
    return cap


# ─── Grounding ────────────────────────────────────────────────────────────────

def _claims(explanation: str) -> tuple[list[str], list[float]]:
    """Checkable claims: proper-noun phrases and numeric values."""
    names = []
    for m in _PROPER_RE.finditer(explanation):
        phrase = m.group(0)
        words = [w for w in phrase.split() if w not in _STOP_CAPS]
        if words:
            names.append(" ".join(words))
    nums = [float(n) for n in _NUM_RE.findall(explanation)]
    return names, nums

def _norm_word(w: str) -> str:
    w = w.lower().strip(".,;:'’-")
    for poss in ("'s", "’s"):
        if w.endswith(poss):
            w = w[: -len(poss)]
    return w

def _source_text(cycle: dict) -> str:
    parts = [json.dumps(cycle.get("trigger", {})), cycle.get("context_text", ""),
             cycle.get("query", "")]
    parts += [e.get("text", "") for e in cycle.get("evidence", [])]
    return " ".join(parts).lower()

def _source_numbers(source: str) -> list[float]:
    return [float(n) for n in _NUM_RE.findall(source)]

def _num_grounded(n: float, source_nums: list[float]) -> bool:
    """A number is grounded if it (or its percent/fraction twin) appears in
    the sources — explanations say '65%' where captures say 0.65."""
    for cand in (n, n / 100.0, n * 100.0):
        for s in source_nums:
            if abs(cand - s) <= max(0.005, abs(s) * 0.01):
                return True
    return False

def grounding_score(cycle: dict) -> tuple[float | None, list[str]]:
    """(score in [0,1] or None if no checkable claims, ungrounded claim list)."""
    explanation = cycle.get("verified_explanation") or cycle.get("raw_explanation", "")
    names, nums = _claims(explanation)
    if not names and not nums:
        return None, []
    source = _source_text(cycle)
    source_nums = _source_numbers(source)
    ungrounded: list[str] = []
    total = grounded = 0
    for name in names:
        total += 1
        # Grounded if every word of the phrase appears in the sources
        # (token-based, so surnames-only mentions pass — verifier parity).
        if all(_norm_word(w) in source for w in name.split()):
            grounded += 1
        else:
            ungrounded.append(name)
    for n in nums:
        total += 1
        if _num_grounded(n, source_nums):
            grounded += 1
        else:
            ungrounded.append(str(n))
    return grounded / total, ungrounded


# ─── Timeliness ───────────────────────────────────────────────────────────────

def timeliness(cycle: dict) -> dict:
    out = {"latency_ms": cycle.get("latency_ms")}
    trig = cycle.get("trigger", {})
    ev = trig.get("market_event") or trig.get("fight_event") or {}
    try:
        out["e2e_ms"] = int(cycle["ts_ms"]) - int(ev.get("timestamp", 0))
    except (ValueError, TypeError, KeyError):
        out["e2e_ms"] = None
    return out


# ─── Outcome consistency ─────────────────────────────────────────────────────

def outcome_consistency(cycle: dict, cap: Capture,
                        window_ms: int = 600_000,
                        flat_eps: float = 0.005) -> str:
    """Did the market continue in the explained direction, revert, or stay
    flat within window_ms after the explanation? 'unknown' without path data."""
    trig = cycle.get("trigger", {})
    m = trig.get("market_event")
    if not m:
        return "unknown"
    market_id = m.get("market_id", "")
    try:
        delta = float(m.get("delta", 0.0))
        p0 = float(m.get("probability", 0.0))
        t0 = int(cycle["ts_ms"])
    except (TypeError, ValueError, KeyError):
        return "unknown"
    after = [(t, p) for t, p in cap.price_path(market_id) if t0 < t <= t0 + window_ms]
    if not after or delta == 0.0:
        return "unknown"
    move = after[-1][1] - p0
    if abs(move) < flat_eps:
        return "flat"
    return "continued" if (move > 0) == (delta > 0) else "reverted"


# ─── Aggregate report ─────────────────────────────────────────────────────────

def _pct(xs: list, q: float):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]

def evaluate(cap: Capture) -> dict:
    """Score every cycle and aggregate — including the PASS/FAIL separation
    check that is B-002's kill criterion."""
    rows = []
    for c in cap.cycles:
        g, ungrounded = grounding_score(c)
        rows.append({
            "trigger_key": c.get("trigger_key"),
            "passed": bool(c.get("passed")),
            "grounding": g,
            "ungrounded_claims": ungrounded,
            **timeliness(c),
            "outcome": outcome_consistency(c, cap),
        })

    def _scores(passed: bool) -> list[float]:
        return [r["grounding"] for r in rows
                if r["passed"] is passed and r["grounding"] is not None]

    pass_scores, fail_scores = _scores(True), _scores(False)
    lat = [r["latency_ms"] for r in rows if isinstance(r["latency_ms"], int)]
    outcomes = defaultdict(int)
    for r in rows:
        outcomes[r["outcome"]] += 1

    held = emitted = 0
    markets = set()
    for poll in cap.polls:
        for s in poll.get("snapshots", []):
            markets.add(s.get("market_id"))
            if s.get("action") == "held":
                held += 1
            elif s.get("action") == "emitted":
                emitted += 1

    return {
        "n_polls": len(cap.polls),
        "n_markets": len(markets),
        "ticks_held": held,
        "ticks_emitted": emitted,
        "n_cycles": len(rows),
        "n_skips": len(cap.skips),
        "n_errors": len(cap.errors),
        "cycles": rows,
        "grounding_mean_pass": sum(pass_scores) / len(pass_scores) if pass_scores else None,
        "grounding_mean_fail": sum(fail_scores) / len(fail_scores) if fail_scores else None,
        "separation": (sum(pass_scores) / len(pass_scores) - sum(fail_scores) / len(fail_scores))
                      if pass_scores and fail_scores else None,
        "latency_ms_p50": _pct(lat, 0.50),
        "latency_ms_p95": _pct(lat, 0.95),
        "outcomes": dict(outcomes),
    }
