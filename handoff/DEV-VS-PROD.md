# Developing vs. Production — how to not break the live site

The production site (**agentpredictmma.com**) and your development environment
run on the same machine, but they are now **fully isolated stacks**. This doc
is the workflow: what's always safe, what's gated, and how a change travels
from your editor to the public site.

## The two stacks at a glance

|                | DEV (yours to break)         | PROD (the live site)            |
|----------------|------------------------------|---------------------------------|
| Start          | `make demo` / `make up`      | `scripts/deploy.sh` **only**    |
| Containers     | `apdev-engine`, `apdev-dash`, … | `ap-engine`, `ap-dash`, `ap-tunnel`, … |
| Network        | `agentpredict_dev_net`       | `agentpredict_net`              |
| Images         | `agentpredict-*:dev`         | `agentpredict-*:prod`           |
| Ports          | 5173 (Vite), 8000 (gateway), 50051 (engine) | 8080 (nginx site) + Cloudflare Tunnel |
| Source of code | whatever is in your tree     | the **git commit** deploy.sh built |
| Stop           | `make down` (always safe)    | `make down-prod` (typed confirmation) |

Why this can't cross the streams:
- Dev commands only ever create/remove `apdev-*` containers on the dev
  network. They don't know prod's names exist.
- Prod containers run `:prod` image tags, which **only `deploy.sh` builds**.
  You can rebuild `:dev` images fifty times; prod keeps running the bits it
  was deployed with.
- Ports don't overlap, so both stacks serve side by side.

## Day-to-day development loop

```bash
# 1. Branch off (never develop on the deployed branch's tip if others share it)
git checkout -b my-feature

# 2. Bring up a dev stack — synthetic data, no API keys, instant:
make demo                # or: scripts/run-stack.sh mock
#    …or against real APIs (shares the same .env keys — see “blast radius”):
make up                  # or: scripts/run-stack.sh real

# 3. Edit code. To see a change, rebuild that image and re-run the dev stack:
podman build -t agentpredict-agents:dev -f agents/Dockerfile .   # (whichever changed)
scripts/run-stack.sh mock
podman image prune -f    # small disk — prune after rebuild cycles

# 4. Look at it: http://localhost:5173   (gateway: http://localhost:8000/health)

# 5. Test before committing:
PINECONE_API_KEY=fake GOOGLE_API_KEY=fake PINECONE_INDEX_NAME=agentpredict \
  .venv-test/bin/pytest agents/tests/unit rag/tests/unit gateway/tests/unit
podman run --rm -v "$PWD/dashboard":/app:z -w /app node:20-slim \
  bash -c 'npx vitest run && npx tsc --noEmit'

# 6. Commit. Dev stack down when you're done:
make down
```

Nothing in that loop can touch the live site.

## Shipping to production

```bash
git checkout samad && git merge my-feature    # (or however you integrate)
make deploy                                    # = scripts/deploy.sh
```

`deploy.sh` is the promotion gate. It will:

1. **Refuse a dirty tree** — prod only runs committed code, so the site is
   always reproducible from git (`--dirty` overrides, don't make it a habit).
2. **Ask you to type `deploy`** — no accidental prod restarts from shell
   history (`--yes` for automation).
3. Build all `:prod` images from your commit, labeled with the git SHA.
4. Swap the prod stack (≈30–60 s downtime; the Cloudflare Tunnel reconnects
   itself) and **verify `/health` goes green** before declaring success — if
   it doesn't, it exits nonzero and tells you which logs to read.
5. Print the deployed SHA. `podman image inspect agentpredict-gateway:prod
   --format '{{index .Labels "org.agentpredict.git-sha"}}'` answers "what's
   live right now?" at any time.

**Rollback** = deploy the previous commit:

```bash
git checkout <last-good-sha> && scripts/deploy.sh && git checkout -
```

## What still overlaps (the honest fine print)

- **One `.env`.** `make up` (dev-real) uses the same API keys as prod, so a
  dev-real stack doubles the Polymarket/BallDontLie polling and can spend
  Gemini/Pinecone quota if odds move. Prefer `make demo` (mock) for UI and
  plumbing work; use dev-real only when you're specifically testing the
  integrations. For full isolation, put separate keys in a `.env.dev` and run
  the containers with `--env-file .env.dev`.
- **One Pinecone index.** A dev-real RAG writes to the same index as prod.
  Set `PINECONE_INDEX_NAME=agentpredict-dev` in your environment for dev-real
  sessions if that bothers you.
- **One small disk.** Builds are shared machinery — build serially and
  `podman image prune -f` after; a full disk takes down builds for both
  stacks (never the *running* site, but you can't deploy off a full disk).
- **One machine.** A crashed host takes both stacks down. Prod restarts by
  running `scripts/run-stack.sh prod --yes` (or a redeploy) after boot.

## Cheat sheet

| I want to… | Command | Can it hurt prod? |
|---|---|---|
| Hack on the UI/pipeline | `make demo` | No |
| Test against real APIs | `make up` | No (but shares API quotas/keys) |
| Stop my dev stack | `make down` | No |
| See what's live | `curl -s https://agentpredictmma.com/health` | No |
| Ship my commit | `make deploy` | Yes — that's its job (gated) |
| Take the site down | `make down-prod` | Yes (typed confirmation) |
| Rebuild a `:dev` image | `podman build …:dev …` | No — prod runs `:prod` |
