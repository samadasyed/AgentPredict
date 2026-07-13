# Proposal (for Samad): persist flight-recorder captures out of containers

**From:** saify · **Files touched:** `docker-compose.yml`, `scripts/run-stack.sh` — your ownership, so this is a proposal, not a commit.

**Context:** B-001 (RESEARCH/BETS.md) added an env-gated flight recorder to the polymarket agent and RAG orchestrator (`RESEARCH_CAPTURE=1` in `.env`, already propagates via `env_file`/`--env-file`). It writes JSONL to `research_capture/` **inside the container filesystem** — which is destroyed on container removal, i.e., every deploy. Fight-night captures are the point, and they're unrecoverable if lost.

**Ask:** bind-mount the capture dir for the two capturing services (both have `WORKDIR /app`).

`docker-compose.yml` — add to `polymarket-agent` and `rag` services:

```yaml
    volumes:
      - ./research_capture:/app/research_capture
```

`scripts/run-stack.sh` — add to the polymarket-agent and rag `run` invocations (real/prod modes):

```bash
    -v "$PWD/research_capture:/app/research_capture" \
```

**Safety:** dir is gitignored; capture is off unless `RESEARCH_CAPTURE=1`; writes are best-effort (a mount problem degrades to a single warning log, never touches the serving path). Disk: ~25 MB per fight night. Rootless podman note: if UID mapping blocks writes, `podman unshare chown` on the host dir or `:U` volume flag fixes it.

**Until merged:** captures only survive on non-containerized runs (e.g., running the agent/rag processes directly) — fine for saify-local dev, not for the prod box.
