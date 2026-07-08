# Dashboard PRODUCTION image — static Vite build served by nginx.
#
# nginx also fronts the gateway: it proxies /ws (WebSocket) and /health to the
# gateway container, so the public site is a single origin — the browser
# derives wss://<host>/ws automatically (no VITE_GATEWAY_WS_URL baked in).
#
# Build context is ./dashboard.
#   podman build -t agentpredict-dashboard:prod -f dashboard/Dockerfile ./dashboard

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-slim AS build

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build          # emits static site to /app/dist

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD wget -q -O /dev/null http://localhost/ || exit 1
