# AgentPredict MMA — Project Overview

*The five-minute version, for humans. Component internals live in
[`agentdocs/`](../agentdocs/); operations in [`handoff/`](../handoff/).*

## What it is

A real-time dashboard for MMA prediction markets. It answers three questions:

1. **What are the odds right now?** Every fight Polymarket lists, with each
   fighter's implied win probability, updating live.
2. **How did they get here?** A 7-day price trend per fight — you can see the
   line move after weigh-ins, injury news, or sharp money.
3. **Why did they just move?** An AI pipeline watches the stream and posts a
   short, evidence-grounded explanation whenever a line makes a real move.

During live events a fourth answer appears: **what's happening in the cage** —
per-fighter significant strikes, takedowns, knockdowns, and control time,
fused next to the swinging odds.

## How data flows, in one paragraph

Two small Python pollers watch the outside world — one asks Polymarket for
fight markets and prices, one asks BallDontLie for card schedules and (on the
paid tier) live fight stats. Everything they see becomes a typed protobuf
event sent to a C++ engine, which validates it (timestamps, ranges, required
fields), stamps it with an ID, and keeps it in a ring buffer while streaming
it onward. Two consumers subscribe: a web gateway that fans events out to
browsers over a WebSocket, and a RAG orchestrator that decides which odds
moves deserve an AI explanation, generates one with Gemini grounded in
retrieved evidence from Pinecone, verifies it, and publishes it through the
same gateway. The React dashboard renders both streams.

## Why some design choices look odd (they're deliberate)

- **Odds history rides inside events, not as back-dated events.** The engine
  rejects any event whose timestamp is more than 60s from now (defense against
  clock skew and replays), so a week of history ships as a snapshot field on a
  current event.
- **The wire has "sentinel" fight events** (`FIGHT_UPCOMING`) that announce
  scheduled cards. They're re-sent periodically so a browser that connects
  late still learns the schedule — every consumer must treat them as schedule
  markers, never as real fight stats.
- **Markets re-announce themselves** every couple of minutes even when odds
  are flat, for the same late-joiner reason.
- **The AI is deliberately conservative.** It triggers on cumulative movement,
  is capped per market per 90 seconds, must ground itself in provided data,
  and a verifier throws away anything low-confidence or off-topic. An empty
  predictions panel on a quiet day is correct behavior.

## Try it in two minutes

```bash
make demo     # no API keys — synthetic fight card with a live main event
```

Open http://localhost:5173: a live fight with swinging odds and play-by-play,
a slate of upcoming fights with countdowns and price trends, and AI analyses
appearing as the (synthetic) lines move.

## Glossary

| Term | Meaning |
|---|---|
| Implied probability | A market price of $0.665 on "Fighter X wins" ≈ 66.5% chance |
| Moneyline market | The fight-winner market (vs. props like method-of-victory) |
| Phase | Where a fight is in its lifecycle: `upcoming`, `live`, `final` |
| Sentinel event | A schedule/discovery marker on the fight-event stream, not a stat |
| Baseline event | A delta-0 odds reading emitted for visibility, not movement |
