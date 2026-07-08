# AgentPredict — Project Handoff

Written 2026-07-08. This directory is the **current-state** snapshot of the project —
everything needed to pick the work back up. (The older `agentdocs/` are the original
June-3 skeleton specs and are stale; trust these files where they disagree.)

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the system fits together, the data
  contracts, and the non-obvious constraints that shaped the design.
- **[RUNBOOK.md](RUNBOOK.md)** — how to build, run, test, debug, and switch between
  mock and real modes on this machine.

---

## What AgentPredict is

A real-time UFC prediction dashboard. It fuses **Polymarket betting odds** with
**live fight statistics** (BallDontLie MMA API), streams both through a C++ event
engine, and uses an agentic **RAG layer** (Pinecone + Gemini) to generate plain-English
explanations of *why* the odds are moving. The product story is a fight-card
lifecycle: browse **upcoming** fights up to a week+ out (countdowns + a week of odds
history), then when a fight goes **live**, watch odds swing alongside a play-by-play
of strikes/takedowns/knockdowns.

## Current status (2026-07-08)

- **Everything is built and working end-to-end** in both mock and real modes.
- **Branch:** `samad` (commits are made here, not `main`; **not pushed** — Samad
  decides when to push). Latest commits:
  - `b31b3fe` Richer demo mock: full UFC card (live main event + stacked upcoming slate)
  - `1788ccc` Real upcoming-fight discovery from BallDontLie; UFC-focused real mode
  - `b59be23` Add fight-card lifecycle: pre-event odds story + live fight tracker
- **The stack was left RUNNING in MOCK mode** (demo for friends): dashboard on
  `localhost:5173`, gateway on `localhost:8000`. From a laptop:
  `ssh -N -L 5173:localhost:5173 -L 8000:localhost:8000 samad@100.91.26.104`
- **Test baseline (all green):** 47 C++ engine tests, 77 Python tests
  (agents + rag + gateway), 39 dashboard vitest tests, `tsc` clean.
- **Real mode verified live:** 5 real upcoming UFC cards flowing from BallDontLie
  with real countdowns; Polymarket agent correctly reports "no on-theme (UFC)
  markets trading right now" when nothing is listed (expected — see below).

## Decisions Samad has made (don't re-litigate)

1. **No BallDontLie tier upgrade for now.** `/fights` and `/fight_stats` are 401
   (plan-gated, GOAT tier ~$39.99/mo). Live round-by-round stats stay dormant in
   real mode until he upgrades; the UI is built to light up automatically when
   `BALLDONTLIE_GOAT_TIER=1` and the key allows it.
2. **UFC only.** Promotion filter stays `MMA_PROMOTION=UFC`; the Polymarket
   off-theme fallback stays off (`POLYMARKET_FALLBACK_ALL=0`).
3. **Working style:** broad autonomy granted ("finish the project"), build with
   mocks first and connect real APIs at the end, never paste API keys in chat
   (`.env` is gitignored and must stay uncommitted).

## Real-data reality (verified against live APIs)

- **BallDontLie MMA:** `/events` works on Samad's key and returns real UFC cards.
  `/fights` and `/fight_stats` → HTTP 401 on his plan. So real mode discovers
  upcoming cards from `/events` and emits `FIGHT_UPCOMING` sentinels; per-fight
  live stats need the tier upgrade.
- **Polymarket:** UFC fight markets typically list only **close to the event** —
  on most days there are zero live UFC markets (politics/World Cup dominate the
  active list). The dashboard shows honest placeholders ("odds not yet listed")
  until markets appear, then merges them with the BallDontLie schedule.

## Likely next steps (nothing is in-flight)

- Flip back to real mode when demoing is done:
  `scripts/stop-stack.sh && RUNTIME=podman scripts/run-stack.sh real`
- If Samad upgrades BallDontLie to GOAT tier: set `BALLDONTLIE_GOAT_TIER=1` in
  `.env` — live stats polling and the Live Fight Tracker should work with no code
  changes (mock mode already exercises that whole path).
- Push `samad` branch / open a PR to `main` — only when Samad asks.
- A real UFC event weekend is the natural end-to-end validation: Polymarket
  markets appear, phases flip `upcoming → live`, RAG explains the swings.
