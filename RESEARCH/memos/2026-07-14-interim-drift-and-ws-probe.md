# Interim — first live drift read + B-003 websocket probe (2026-07-14)

Mid-week working note while the first real capture accumulates (full analysis lands in cycle 4 after the Jul 18 card). Three findings, one correction, one bet promotion.

## Drift findings (~75 min, quiet pre-fight Tuesday, 23 markets)

Tooling: `RESEARCH/harness/drift.py` (per-market path stats + what-if emit counts at 0.002/0.005/0.01/0.02 for both the per-tick and cumulative gates; 6 harness tests green).

1. **All observed movement was below the production threshold.** Only 3/23 markets moved at all; every move was exactly 0.005; at `DELTA_THRESHOLD=0.01` there were **zero emits** — the product was blind to 100% of the afternoon's activity, while a 0.002–0.005 threshold would have surfaced 4 real moves. Not yet a tuning recommendation — fight-night data decides — but it's the first quantified evidence.
2. **These low-volume markets tick on a half-cent (0.005) grid**, so the 0.01 threshold needs two grid steps to fire. Threshold tuning must be grid-aware.
3. **Correction of an earlier estimate:** measured inter-poll gaps are **p50 5.2s / mean 5.5s / p99 7.2s** — the poller performs as configured; my earlier "~10s effective cadence" claim was wrong (bad window arithmetic). One 89.8s stall outlier observed (likely the market-list cache refresh path) — watch for recurrence on fight night.

## B-003 feasibility probe: CLOB market websocket — POSITIVE

120s live probe against `wss://ws-subscriptions-clob.polymarket.com/ws/market`, subscribed to 3 fight-market tokens (Usman–Du Plessis, Cannonier–Duncan, Bashi–Delgado). Result: **public, no auth, connected first try; 3 `book` snapshots + 62 `price_change` events in 2 minutes** — on the same quiet markets where our poller emitted nothing. The WS pushes order-book-level changes in real time vs our 5s midpoint samples. (Probe's per-change field parsing needs fixing — payload schema differs from my guess — cosmetic, doesn't affect the finding.)

**Decision: B-003 promoted backlog → active.** Cheapest decisive experiment: run a WS side-recorder in parallel with the poll capture through fight night and measure (a) lead time of WS ticks over poll detection on real moves, (b) whether WS-only information (book pressure before midpoint moves) exists. Kill criterion: WS shows no material lead over 5s polling on fight-night moves, or proves too unreliable (disconnects/gaps) to run unattended.

## State

- Poll capture: running continuously (23 markets, ~453 polls so far today).
- Next: WS side-recorder before Saturday; cycle-4 full analysis ~Jul 19.
- Still on others: Samad merge of `d75d64b` + prod `RESEARCH_CAPTURE=1`; fresh Pinecone key.
