# Deploying to agentpredictufc.com

The production stack is real-API only: Polymarket Gamma (no key), BallDontLie
(`BALLDONTLIE_API_KEY`), Gemini (`GOOGLE_API_KEY`), Pinecone
(`PINECONE_API_KEY`). Everything runs from containers; the only public surface
is the dashboard's nginx, which serves the built SPA **and** proxies `/ws` +
`/health` to the gateway — one origin, so the browser derives `wss://…/ws`
automatically.

```
internet ──TLS──▶ host proxy / LB ──▶ dashboard nginx :80
                                        ├── /            static SPA (Vite build)
                                        ├── /ws          → gateway:8000 (WebSocket)
                                        └── /health      → gateway:8000
                     engine :50051, rag :50052, gateway :8000 — internal only
```

## Option A — Docker VPS (recommended)

```bash
git clone <repo> && cd AgentPredict
cp .env.example .env          # fill in the three API keys; never commit .env
docker compose -f docker-compose.prod.yml up -d --build
```

- Serves on `:80`. Put TLS in front (either change the port mapping and run a
  host Caddy — `agentpredictufc.com { reverse_proxy localhost:8080 }` is the
  entire Caddyfile — or use the cloud load balancer).
- `GATEWAY_ALLOWED_ORIGINS` is pinned in the compose file to
  `https://agentpredictufc.com,https://www.agentpredictufc.com`. Add origins if
  the site gets others; an empty value means allow-any (dev only).
- All services `restart: always`; gateway healthcheck is honest (503 when the
  engine or RAG stream is down/silent — wire it to uptime monitoring).

## Option B — this podman host (no compose)

```bash
scripts/run-stack.sh prod     # nginx site on :8080, everything else internal
```

Rootless podman can't bind :80, so prod mode publishes `:8080`. Point the TLS
terminator at it. Set `GATEWAY_ALLOWED_ORIGINS` in `.env` (run-stack passes
`.env` to the gateway in prod mode).

## DNS + TLS checklist

1. `A`/`AAAA` records for `agentpredictufc.com` and `www` → server IP.
2. TLS via Caddy (automatic Let's Encrypt) or certbot + nginx.
3. The proxy must forward WebSocket upgrades to `/ws` (Caddy does by default;
   for host nginx copy the `location /ws` block from `dashboard/nginx.conf`).
4. After cutover: `curl https://agentpredictufc.com/health` → `{"status":"ok",…}`
   and the site shows LIVE in the header.

## Ops notes

- **Cost guards**: `RAG_MARKET_COOLDOWN_S` (default 90) caps Gemini calls to
  ~1/market/1.5min during live swings; `RAG_MAX_UPSERTS_PER_HOUR` caps Pinecone
  growth. Raise/lower in `.env`.
- **Live fight stats** stay dormant until `BALLDONTLIE_GOAT_TIER=1` **and** the
  key's plan actually unlocks `/fights` + `/fight_stats` (else 401 → graceful
  empty). Odds, schedules, countdowns, histories, and AI predictions all work
  on the current plan.
- **Quiet weeks are normal**: Polymarket lists fight markets days (not months)
  ahead. With no listed fights the site shows upcoming cards from BallDontLie
  with "odds not yet listed".
- **Health semantics**: `/health` 200 = both gRPC subscribers connected and the
  engine stream not silent >`GATEWAY_ENGINE_SILENCE_S` (180s). 503 body says
  which side is degraded and why.
- **Logs**: `docker compose -f docker-compose.prod.yml logs -f gateway` (or
  `podman logs -f ap-gateway` etc.).
