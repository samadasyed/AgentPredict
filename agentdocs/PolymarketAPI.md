# Polymarket API Notes (verified 2026-07)

Base URLs: Gamma `https://gamma-api.polymarket.com`, CLOB
`https://clob.polymarket.com`. No API key. **A browser User-Agent is
required** — default HTTP-library UAs get 403 at the edge.

## Fight discovery — tagged events
`GET /events/pagination?tag_slug=ufc&closed=false&limit=100` → `{data: [...]}`.
One event per fight, e.g. title `"UFC 329: Max Holloway vs. Conor McGregor
(Welterweight, Main Card)"`, with `slug`, `startTime` (ISO Z), `volume`, and
embedded `markets[]`.

- **Use `/events/pagination`.** Bare `/events` (and `/markets`) return
  `deprecation: true` with a Sunset date already in the past.
- The fight-winner market is `markets[].sportsMarketType == "moneyline"`
  (exactly one per fight event). Other types: `ufc_method_of_victory`,
  `ufc_go_the_distance`, `totals`.
- Market `outcomes`/`outcomePrices`/`clobTokenIds` are **JSON strings**, not
  arrays — parse them.
- `gameStartTime` uses `"2026-07-11 22:00:00+00"` (space separator, short
  offset); event `startTime` uses `"...T...Z"`. Parse both.
- Speculative events ("Who will X fight next?", futures) share the tag —
  filter by title shape `"<card>: <A> vs. <B> (<info>)"`.
- Events can linger open after a card change (opponent swap): drop fights
  whose start passed >12h ago but never closed.

## Price history — CLOB
`GET /prices-history?market=<clobTokenId>&interval=1w&fidelity=180` →
`{history: [{t: epoch_seconds, p: probability}]}`.
**`fidelity` (minutes/point) is required** for ranged intervals — `1w`
rejects <5 with HTTP 400. 180 → ~57 points/week.

## Linking to the site
`https://polymarket.com/event/<event slug>`.
