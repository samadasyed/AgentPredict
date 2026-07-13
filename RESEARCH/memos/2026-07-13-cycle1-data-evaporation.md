# Cycle 1 — What the system knows but throws away (2026-07-13)

**Question investigated:** During a live fight card, what data flows through AgentPredict and evaporates? Can an explanation-quality eval harness be built from replayable real data?

**Verdict:** The system discards essentially 100% of its most valuable data. Both proposed moats — the correlation dataset and the eval harness — are blocked on the same missing primitive: a persistent capture layer. It fits entirely in saify's lane (`agents/polymarket/`, `rag/`), needs no wire-contract changes, and should exist **before the next fight card**, because the data only exists a few days per month.

## Evidence: six leaks, all verified in current code

1. **Sub-threshold price ticks are discarded.** The Polymarket agent polls up to 30 markets every 5s but emits only `|Δ| ≥ 0.01` moves plus 120s baselines (`agents/polymarket/agent.py:130-148`). The full 5s-resolution price path lives one poll in `_price_cache`, then is overwritten. During a live fight this is exactly the microstructure data (lead/lag vs fight events) nobody else is collecting.
2. **Week-long CLOB price histories are fetched, used once, dropped.** `_fetch_history` pulls 1-week/5-min-fidelity histories per market (`agents/polymarket/client.py:280-294`), caches them in memory for 300s, ships them in the proto snapshot, and never persists them. We repeatedly download a dataset we could be accreting.
3. **The engine retains at most 4096 events, in memory.** `EventStore(capacity = 4096)` (`engine/src/event_store.hpp:24`). A restart or a busy card wipes it. Not our lane to change — and we don't need to: capture belongs at the edges we own.
4. **Every RAG cycle's artifacts evaporate.** In `rag/orchestrator.py::_run_cycle` (lines 346-386): context text, retrieval query, evidence + scores, raw explanation, confidence, and the verifier outcome exist only in local variables and log lines. **Failed verifications — the most diagnostic data for improving the pipeline — are logged and lost** (line 369).
5. **Skipped triggers aren't recorded.** Cooldown/busy skips (`_should_run_cycle`, lines 289-299) are the counterfactuals an eval harness needs ("what would we have said here?") — currently `logger.debug` only.
6. **`DEBUG_DUMP` is not a capture layer.** It dumps raw HTTP JSON to `/tmp/polymarket_debug` off by default (`agents/polymarket/client.py:55-56, 245-248`) — unstructured, truncated at 200KB, client-side only. Useful precedent (env-gated dumping is already accepted in this codebase), not a substitute.

## Live drift check (budget: 1 request)

Gamma `/events/pagination?tag_slug=ufc` healthy on 2026-07-13: 46 active events, but all inspected are futures ("who fights next", "champion at end of 2026") — correctly rejected by the title-shape filter. UFC 329's fight markets (Jul 11) are gone. **Implication: the moat data has a scarce capture window (fight week only). Every card that passes without capture is unrecoverable.**

## Eval harness feasibility

Everything a harness needs already passes through code we own. Two tap points suffice:

- **Tap A (agent):** in `_poll_once`, append every `PriceSnapshot` (not just emitted ones) to a JSONL file — full 5s price paths, plus the fetched week histories once per TTL.
- **Tap B (orchestrator):** in `_run_cycle` + skip paths, append one JSONL record per trigger: trigger event, cumulative delta, context text, retrieval query, evidence+scores, raw explanation, confidence, verifier outcome (incl. FAILs), latency, and skip reasons.

Env-gated (`RESEARCH_CAPTURE=1`, `RESEARCH_CAPTURE_DIR`), append-only JSONL, best-effort writes (a capture failure must never break the serving path), off by default, fully mockable in unit tests. Zero proto/gateway/dashboard changes. Disk math: even an aggressive fight night (~30 markets × 12 polls/min × ~500B) is ≈ 25 MB/day — negligible.

With capture in place, the harness is an offline job: replay captured triggers through the pipeline (mock or real inference), score explanations on (a) grounding — every factual claim traceable to captured context/evidence, (b) timeliness — explanation latency vs the price move, (c) outcome consistency — did the subsequent captured price path/fight result corroborate the explanation. (a) and (b) are computable without any labeling; (c) is free ground truth that only exists if we captured the path.

## Bet changes

- **Opened B-001 (flight recorder / correlation dataset)** — the prerequisite for everything else. See BETS.md.
- **Opened B-002 (explanation eval harness)** — depends on B-001's first real capture.
- **Backlogged B-003 (CLOB websocket latency edge)** — real but sequenced behind capture: without recorded price paths we can't even measure what latency the 5s poll costs us.

## Recommendation (one, ranked by impact on the standing question)

**Build the flight recorder this week, before the next UFC card lists.** It is ~a day of work in our lane, env-gated and invisible to the serving path, and it converts every future fight night from an ephemeral demo into an accreting proprietary dataset — the input to the eval harness, the drift-detection research, the latency analysis, and any future model the company trains. Per house rules this needs saify's go-ahead before source edits; the design above is the proposal.
