# Agent Doc — React Dashboard
**Owner:** Zaid
**Component:** `dashboard/`
**Stack:** React 18, Vite 5, TypeScript 5, Tailwind CSS 3, Vitest
**Role:** Receive two WebSocket streams from the gateway and display them in a two-column layout. You do not generate, infer, or modify data — only display it faithfully.

---

## What's Already Done

| File | Status |
|---|---|
| `package.json` | Complete — all deps defined |
| `vite.config.ts` | Complete — dev server :5173, `/ws` proxy to gateway, Vitest config |
| `tsconfig.json` | Complete |
| `tailwind.config.ts` | Complete — custom color tokens (`pm`, `mma`, `confidence`) |
| `postcss.config.js` | Complete |
| `index.html` | Complete |
| `src/index.css` | Complete — Tailwind directives |
| `src/main.tsx` | Complete |
| `src/App.tsx` | Complete — wires hook + layout + warnings |
| `src/types/events.ts` | Complete — TS mirrors of proto event shapes |
| `src/types/rag.ts` | Complete — TS mirrors of RagPrediction shape |
| `src/hooks/useEventStream.ts` | Complete — WS lifecycle, message routing, reconnect |
| `src/components/layout/Header.tsx` | Complete — title + connection indicator |
| `src/components/layout/TwoColumnLayout.tsx` | Complete |
| `src/components/events/SourceBadge.tsx` | Complete — blue PM / orange MMA pill |
| `src/components/events/EventCard.tsx` | Complete — renders market and fight events |
| `src/components/events/EventFeed.tsx` | Complete |
| `src/components/predictions/EvidenceList.tsx` | Complete |
| `src/components/predictions/PredictionCard.tsx` | Complete — explanation + confidence bar + evidence |
| `src/components/predictions/PredictionFeed.tsx` | Complete |
| `src/components/shared/StreamWarning.tsx` | Complete — amber banner |
| `src/tests/hooks/useEventStream.test.ts` | Complete — 7 Vitest tests |
| `src/tests/components/EventCard.test.tsx` | Complete — 7 render tests |
| `src/tests/components/PredictionCard.test.tsx` | Complete — 7 render tests |
| `dashboard/Dockerfile.dev` | **Missing — you need to create this** |

---

## First Thing: Install Dependencies

```bash
cd dashboard
npm install
npm run dev     # starts dev server on http://localhost:5173
```

The dev server proxies `/ws` → `ws://localhost:8000/ws` automatically (configured in `vite.config.ts`). You don't need the gateway running to develop — see [Local Dev Without Gateway](#local-dev-without-gateway) below.

---

## Your TODOs

### 1. Create `dashboard/Dockerfile.dev`

Docker Compose references this. It needs to:
- Base: `node:20-slim`
- `WORKDIR /app`
- Copy `package.json` + `package-lock.json`, run `npm install`
- Copy everything else
- `EXPOSE 5173`
- `CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]`

### 2. Local Dev Without Gateway (`src/hooks/useEventStream.ts`)

Currently the hook connects directly to the real gateway. Add a mock WebSocket server or a `VITE_MOCK_WS=true` mode so Zaid can develop UI without the full backend running. One approach: create `src/tests/mockWsServer.ts` that emits fake events on an interval, and conditionally use it in dev mode.

### 3. Client-side filtering (optional, `gateway/server.py` also has TODO)

The gateway `server.py` has a stub for handling client filter messages:
```ts
// TODO: handle client-side filter messages (e.g. {"action": "filter", "source": "pm"})
```
If you want to let users toggle between PM/MMA events on the left column, send `{"action": "filter", "source": "pm"}` from the browser. Coordinate with Samad to wire this up on the gateway side.

### 4. Late-join replay

When a browser connects mid-stream, it sees no events until the next one arrives. The gateway has a TODO to buffer the last 50 events. Once Samad implements that, the hook may need to handle a batch of events on first connect. For now, "Waiting for events…" is the correct initial state.

### 5. Additional components (as needed)

The skeleton has the minimum viable component set. Things you might want to add:
- A fight selector / market filter bar at the top
- A market-specific detail panel (click an EventCard to expand)
- A confidence histogram across all predictions
- Timestamps formatted as relative time ("3s ago") rather than wall clock

---

## Stream Rules — Do Not Violate These

These are product requirements, not suggestions.

### Stream 1 (EventFeed — left column)
- **Factual only.** Show what happened: price moved, fight discovered.
- **No predictive language.** Never say "may", "likely", "suggests", or anything inferential on this stream.
- **Distinguish sources visually.** Polymarket events show a blue "PM" badge. MMA events show an orange "MMA" badge. This is already implemented in `SourceBadge.tsx`.
- **Most recent first.** Already implemented in `useEventStream.ts` (prepends to array).

### Stream 2 (PredictionFeed — right column)
- **Always show evidence.** `EvidenceList` must always be rendered — never hidden or collapsed by default.
- **Keep confidence honest.** The confidence bar uses green (>70%), yellow (50–70%), and gray (<50%). Do not change these thresholds without coordinating with FWS (the verifier uses the same 0.5 threshold).
- **Most recent first.** Same as Stream 1.

### Error states
- **Fail visibly.** If the WebSocket drops, `StreamWarning` must appear immediately. Already wired in `App.tsx`.
- **Malformed payload** (JSON parse error or unknown type) also triggers `StreamWarning`.
- **Never silently swallow errors** — if something goes wrong, the user must see it.

---

## Type Contracts

These TypeScript types in `src/types/` are mirrors of the proto definitions. Do not change field names — they come directly from the gateway's `MessageToDict` output which uses `preserving_proto_field_name=True`.

**`src/types/events.ts`**
```ts
interface CanonicalEvent {
  event_id: string
  source: 'SOURCE_UNKNOWN' | 'SOURCE_POLYMARKET' | 'SOURCE_MMA'
  ingested_at: number       // unix millis
  market_event?: MarketEvent
  fight_event?: FightStatEvent
}

interface MarketEvent {
  market_id: string
  outcome: string
  probability: number       // [0, 1]
  delta: number             // signed
  timestamp: number         // unix millis
}
```

**`src/types/rag.ts`**
```ts
interface RagPrediction {
  explanation: string
  evidence: EvidenceItem[]
  confidence: number        // [0, 1]
  timestamp: number         // unix millis
  trigger_event_id: string
}
```

The gateway wraps these in an envelope: `{ type: "event" | "prediction", data: {...} }`. The hook unwraps the envelope before storing in state — components only ever see the inner `data` objects.

---

## Color Tokens (Tailwind)

Defined in `tailwind.config.ts`:

| Token | Hex | Used for |
|---|---|---|
| `pm` / `text-pm` | `#3B82F6` | Polymarket source badge |
| `mma` / `text-mma` | `#F97316` | MMA source badge |
| `confidence-high` | `#22C55E` | Confidence bar > 70% |
| `confidence-medium` | `#EAB308` | Confidence bar 50–70% |
| Gray (existing) | `#6B7280` | Confidence bar < 50% |

Use these tokens rather than raw hex values in any new components.

---

## `useEventStream` Hook Reference

```ts
const { events, predictions, connected, error } = useEventStream()
```

| Return value | Type | Description |
|---|---|---|
| `events` | `CanonicalEvent[]` | Last 200 events, newest first |
| `predictions` | `RagPrediction[]` | Last 50 predictions, newest first |
| `connected` | `boolean` | WebSocket open state |
| `error` | `string \| null` | Last error message, or null |

The hook reconnects automatically after 3 seconds on disconnect. You do not need to manage the WebSocket anywhere else.

---

## Run

```bash
cd dashboard
npm install
npm run dev          # dev server on :5173
npm test             # Vitest (all tests, no watch)
npm run test:watch   # Vitest in watch mode
npm run build        # production build to dist/
```

**Environment variable:**
```
VITE_GATEWAY_WS_URL=ws://localhost:8000/ws   # default if not set
```

---

## Tests

All tests are in `src/tests/`. Run with:
```bash
npm test
```

Tests use:
- `@testing-library/react` for component rendering
- `vitest` as the test runner (configured in `vite.config.ts`)
- `jsdom` as the DOM environment
- A manual `MockWebSocket` class (defined in `useEventStream.test.ts`) — no real connections made

When writing new component tests, follow the pattern in `EventCard.test.tsx`:
- Import the component directly
- Pass typed props
- Use `screen.getByText` / `toBeInTheDocument` / `toHaveClass` assertions
- Do not test implementation details (state, internal hooks)

When writing new hook tests, follow `useEventStream.test.ts`:
- Use `renderHook` from `@testing-library/react`
- Wrap state changes in `act()`
- Interact with `MockWebSocket.instances[0]` to simulate server messages
