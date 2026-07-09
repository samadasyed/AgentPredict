# Publishing AgentPredict MMA at agentpredictmma.com — Full Guide

The complete path from this server to a live public site, via **Cloudflare
Tunnel**. Dashboard steps verified against Cloudflare's docs on 2026-07-08
(their UI was renamed twice since 2025 — older tutorials will not match).

## How it works

This server has no public IP (it's behind NAT/Tailscale). A Cloudflare Tunnel
inverts the connection: a tiny connector container (`cloudflared`) dials **out**
to Cloudflare and keeps 4 encrypted connections open (spread across ≥2 of their
datacenters); Cloudflare's edge then serves `https://agentpredictmma.com` and
forwards every request back down the tunnel to the site's nginx. No port
forwarding, no inbound firewall holes, TLS handled at the edge, free plan.

```
visitor ──HTTPS──▶ Cloudflare edge ══tunnel (outbound from server)══▶ ap-tunnel
                                                                        │ pod network
                                                                        ▼
                                                              ap-dash (nginx :80)
                                                               ├─ /        static SPA
                                                               ├─ /ws   ──▶ gateway:8000
                                                               └─ /health ─▶ gateway:8000
```

The only egress the connector needs is **port 7844** (UDP for its default QUIC
protocol; it silently falls back to HTTP/2-over-TCP if UDP is blocked — under
rootless podman it may well run on the fallback, which is fine).

## What's already done on the server (verified working)

- ✅ Production stack running: `scripts/run-stack.sh prod` — static-built site
  behind nginx on `:8080`, single origin serving the SPA + proxying `/ws` and
  `/health`; gateway/engine/agents internal-only.
- ✅ `GATEWAY_ALLOWED_ORIGINS=https://agentpredictmma.com,https://www.agentpredictmma.com`
  set in `.env` — cross-site browser WebSockets are rejected (tested), while
  non-browser clients (curl, probes) still work.
- ✅ `run-stack.sh prod` **auto-starts the tunnel connector** (`ap-tunnel`) when
  `CLOUDFLARE_TUNNEL_TOKEN` is set in `.env`; `stop-stack.sh` cleans it up.
- ✅ Real data + AI predictions verified end-to-end; GOAT-tier live stats armed.

So the entire remaining work is the Cloudflare account side, then dropping one
token into `.env`.

---

## Step 1 — Get the domain onto Cloudflare

**Path A (recommended): register it with Cloudflare directly.**
1. Log in at [dash.cloudflare.com](https://dash.cloudflare.com) (create the free
   account with a verified email if you don't have one).
2. Go to **Domains → Register** (search box), search `agentpredictmma.com`,
   **Purchase**. Cloudflare Registrar charges at-cost — roughly **$10–12/yr**
   for a .com; the exact price shows at checkout.
3. Done — the DNS zone is on Cloudflare automatically (Registrar domains always
   use Cloudflare nameservers). No propagation wait.

**Path B: already bought it elsewhere (Namecheap, GoDaddy, …).**
1. Dashboard → **Domains → Onboard a domain** → enter `agentpredictmma.com` →
   pick the **Free** plan.
2. If the registrar has **DNSSEC enabled, disable it there FIRST** (changing
   nameservers with DNSSEC on can take the domain offline).
3. Cloudflare shows two nameservers — set them at your registrar (replace the
   existing ones). Activation takes minutes-to-24h; Cloudflare emails you when
   the zone flips to **Active**.

## Step 2 — Create the tunnel and copy the token

1. Dashboard → **Networking → Tunnels** (this moved: old guides say "Zero Trust
   → Networks → Tunnels"; if your account shows the older layout, look under
   **Networks → Connectors**).
2. **Create Tunnel** → name it `agentpredict` → Create.
3. Under **Setup Environment**, pick **Docker**. It shows an install command
   containing a long token (`eyJ…`). **Copy just the token**, not the whole
   command — our stack script runs the container itself.
4. Leave this page open (it flips to "connected" once we start the connector in
   Step 4).

## Step 3 — Add the published-application routes

Still in your tunnel's page:

1. **Routes** tab → **Add route** → **Published application**.
2. Route 1: leave the subdomain **empty**, select domain `agentpredictmma.com`,
   **Service URL** = `http://ap-dash:80` → Save/Add route.
3. Route 2: subdomain `www`, same domain, same Service URL → Save.

Cloudflare auto-creates the DNS records (CNAMEs to `<tunnel-id>.cfargotunnel.com`)
— no manual DNS work. If saving fails with a DNS-conflict error, delete any
pre-existing A/CNAME records for those names under **DNS → Records** and retry.

`ap-dash` resolves because our script runs the connector on the same podman
network as the site's nginx container — that's why the Service URL is a
container name, not localhost.

## Step 4 — Token into `.env`, start the connector

On the server (**never paste the token into a chat or commit it** — `.env` is
gitignored):

```bash
# put the token in .env (or edit .env in any editor)
sed -i 's|^CLOUDFLARE_TUNNEL_TOKEN=.*|CLOUDFLARE_TUNNEL_TOKEN=eyJ…your-token…|' .env

# restart the stack — prod mode starts ap-tunnel automatically when the token is set
scripts/stop-stack.sh && scripts/run-stack.sh prod
```

The script prints `public → Cloudflare Tunnel connector running`. Within ~30s
the tunnel page in the dashboard shows **Healthy**.

(Equivalent manual command, for reference — mirrors Cloudflare's documented
`docker run … tunnel --no-autoupdate run` adapted to podman + our network:
`podman run -d --name ap-tunnel --network agentpredict_net -e TUNNEL_TOKEN=… docker.io/cloudflare/cloudflared:latest tunnel --no-autoupdate run`)

## Step 5 — One-time zone settings

In the dashboard, for the `agentpredictmma.com` zone:

1. **Network → WebSockets** — confirm the toggle is **On** (the live odds feed
   is a WebSocket; docs don't state the default, so check).
2. **SSL/TLS → Overview** — any mode except **Off** works with a tunnel (new
   zones may show "Automatic SSL/TLS", which is fine). If choosing manually,
   Cloudflare's general guidance is **Full (strict)**.
3. **SSL/TLS → Edge Certificates → Always Use HTTPS: On** — so plain-http
   visits redirect.

## Step 6 — Verify

```bash
curl -s https://agentpredictmma.com/health        # → {"status":"ok",...}
podman logs ap-tunnel | tail -20                  # "Registered tunnel connection" ×4
```

Then from any browser: `https://agentpredictmma.com` — the site should show the
**Live** badge (WebSocket connected through the tunnel), the fight card, and
odds updating. The `www` variant should work identically.

---

## Operations

- **Bring the whole public site up/down:**
  `scripts/run-stack.sh prod` / `scripts/stop-stack.sh` — the tunnel connector
  is part of the stack now.
- **Idle WebSockets:** Cloudflare closes quiet connections after an unpublished
  timeout. Fine for us — during operation events flow every few seconds, and
  the dashboard auto-reconnects within 3s of any close (the gateway replays
  recent history on reconnect, so nothing is missed).
- **Updating the site:** rebuild the changed image(s) (see RUNBOOK.md), then
  `scripts/stop-stack.sh && scripts/run-stack.sh prod`. The tunnel token
  persists in `.env`; the domain comes back automatically.
- **Updating the connector:** `podman pull docker.io/cloudflare/cloudflared:latest`
  then restart the stack (auto-update is disabled in containers by design).
- **Uptime monitoring:** point a free checker (e.g. UptimeRobot) at
  `https://agentpredictmma.com/health` — it returns **503 with reasons** when
  the data plane is degraded, not a hollow 200.
- **Cost guards:** `RAG_MARKET_COOLDOWN_S` (90) caps Gemini spend during live
  swings; `RAG_MAX_UPSERTS_PER_HOUR` caps Pinecone growth. Free-plan Cloudflare
  has no bandwidth cap for normal site traffic (just don't serve video files
  through it).
- **Live fight stats (GOAT tier):** active and verified. If the key ever
  regresses to 401, the site degrades gracefully to odds-only.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Browser shows Cloudflare **Error 1033** | No healthy connector — `podman ps` (is `ap-tunnel` up?), `podman logs ap-tunnel`. Token wrong/rotated → create a new token in the tunnel page, update `.env`, restart |
| Tunnel Healthy but site 502 | Connector can't reach nginx — `ap-tunnel` must be on `agentpredict_net` and `ap-dash` running; Service URL must be exactly `http://ap-dash:80` |
| Site loads, no live data ("Offline" badge) | WS blocked: zone **Network → WebSockets** must be On; SSL/TLS mode must not be **Off**; if Super Bot Fight Mode is enabled, it can kill WS upgrades — turn it off. Also check `https://…/health` for a degraded data plane |
| Everything works on `:8080` locally but not publicly | DNS not active yet (Path B: nameserver propagation, up to 24h) or the published-application route points at the wrong service |
| Tunnel flaps between connects | UDP 7844 blocked → it should auto-fall-back to HTTP/2; if someone forced `--protocol quic`, remove that |
| Saving a route fails with a DNS error | A record already exists at that hostname — delete it under DNS → Records, retry |

## Alternative — Docker VPS (if you outgrow the home server)

```bash
git clone <repo> && cd AgentPredict
cp .env.example .env          # add the API keys
docker compose -f docker-compose.prod.yml up -d --build
```

Serves on `:80` with the same single-origin nginx; put the VPS behind Cloudflare
(orange-cloud DNS A record) or a host Caddy for TLS. All services
`restart: always`. The tunnel approach also works identically on a VPS if you'd
rather keep zero open ports there too.
