# Research Bets — live tracker

Max 2–3 **active** bets at any time. Every bet carries: hypothesis, why we're positioned to win it, cheapest decisive experiment, kill criterion, and what shipping it changes. Killed bets move to the graveyard with an autopsy — a dead end with data is a valid output.

## Active

### B-001 — Flight recorder: capture the correlation dataset
- **Status:** active — proposed to saify (memo [2026-07-13-cycle1](memos/2026-07-13-cycle1-data-evaporation.md)); awaiting go-ahead for source edits
- **Hypothesis:** Persisting the full event-aligned data stream (5s price paths, week histories, fight events, every RAG cycle's inputs/outputs incl. failed verifications and skipped triggers) turns fight nights into an accreting proprietary dataset — the single prerequisite for the eval harness, latency research, and any future in-house model.
- **Why us:** The data already flows through code in saify's lane (`agents/polymarket/agent.py`, `rag/orchestrator.py`); nobody else joins Polymarket microstructure with fight events + explanation traces. Capture windows are scarce (fight week only), so being running > being clever.
- **Cheapest decisive experiment:** Env-gated (`RESEARCH_CAPTURE=1`) append-only JSONL taps at `_poll_once` and `_run_cycle`; verify in mock mode, then let it run through the next real card. ~1 day of work, ~25 MB/fight-night.
- **Kill criterion:** Two captured cards produce data that neither the eval harness (B-002) nor lead/lag analysis can extract signal from, or capture measurably perturbs the serving path.
- **If it ships, the product gains:** A durable data moat that grows every event, plus the raw material for every other bet.
- **Evidence so far:** Six verified data leaks + feasibility design in [2026-07-13-cycle1](memos/2026-07-13-cycle1-data-evaporation.md).

### B-002 — Explanation-quality eval harness
- **Status:** active — design phase; blocked on B-001's first real capture
- **Hypothesis:** Explanation quality can be scored offline without human labeling: grounding (claims traceable to captured context/evidence), timeliness (latency vs the price move), and outcome consistency (subsequent price path / fight result corroborates the explanation). With a score, prompt/threshold/retrieval changes become measurable instead of vibes.
- **Why us:** We own `rag/` end-to-end and the verifier contract; captured failed verifications are a free hard-negative set no competitor has.
- **Cheapest decisive experiment:** Replay one captured fight card's triggers through the pipeline offline (mock + real inference), compute the three scores, and check they discriminate between known-good and known-bad explanations (e.g., verifier PASS vs FAIL populations separate).
- **Kill criterion:** Scores fail to separate PASS from FAIL populations, or grounding checks can't be computed reliably from captured context.
- **If it ships, the product gains:** A regression gate for Stream 2 quality and the ability to claim (and prove) "measurably better than a human watching two screens."
- **Evidence so far:** Tap-point feasibility confirmed in [2026-07-13-cycle1](memos/2026-07-13-cycle1-data-evaporation.md); no captures yet.

## Backlog (not active — do not work these yet)

- **B-003 — CLOB websocket latency edge.** 5s polling vs markets that move in seconds mid-fight. First experiment: verify the public CLOB market websocket channel live during fight week and measure tick latency vs our poll. Sequenced behind B-001 — without captured price paths we can't quantify what the poll costs us.

## Graveyard

_Empty._
