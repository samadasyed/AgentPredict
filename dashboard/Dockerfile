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

# Templated config: the image's stock 15-local-resolvers.envsh (activated by
# the env below) exports NGINX_LOCAL_RESOLVERS from /etc/resolv.conf, then
# envsubst renders the template — so nginx re-resolves `gateway` per-request
# instead of caching one IP at startup (a recreated gateway 502'd the site).
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD wget -q -O /dev/null http://localhost/ || exit 1
