# Invariants — break these and the product breaks

Each rule below has caused (or would cause) a real production bug.

1. **60-second clock-skew guard.** The engine rejects events whose envelope
   timestamp is >60 s from now. Never back-date events; ship history as the
   `history` snapshot field on a now-dated event.
2. **Sentinels are not stats.** `FIGHT_UPCOMING` / `FIGHT_DISCOVERED` are
   re-emitted schedule markers. They must stay excluded from: dashboard live
   aggregation (`SENTINEL_STATS`), the event feed display, and RAG triggering
   (`_SENTINEL_STATS`). Add any new sentinel to all three.
3. **int64 → JSON strings.** MessageToDict serializes int64 as strings.
   Every new time/count field needs `Number()` coercion in the dashboard.
4. **Late joiners see only the replay buffer.** Anything a fresh browser must
   know has to be re-emitted periodically (market baselines, schedule
   sentinels) — a fact sent once at startup effectively doesn't exist.
5. **Proto changes ripple three ways**: regenerate `agents/generated/`
   (recipe in `handoff/RUNBOOK.md`), engine stubs rebuild with its image,
   and `dashboard/src/types/events.ts` is maintained by hand.
6. **AI cost guards stay on**: cumulative-drift trigger + per-market cooldown
   + single-flight + hourly upsert budget. Removing any of them turns a live
   fight night into an unbounded API bill.
7. **Only verified predictions reach users.** The verifier's reject path is
   product behavior, not an error path.
8. **Secrets live in `.env` only** (gitignored). `.env.example` is the
   committed template and must contain placeholders only.
9. **Mocks mirror real shapes.** `MOCK_MODE=1` must exercise the same code
   paths downstream services see in production — same fields, same semantics.
