# AgentPredict — common dev/run targets.
#
# Auto-detects a compose tool (docker compose / podman-compose / podman compose).
# If none is installed, `make demo` / `make up` / `make down` fall back to raw
# `podman run` via scripts/run-stack.sh. Force a specific tool with:
#   make demo COMPOSE="docker compose"
COMPOSE ?= $(shell \
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then echo "docker compose"; \
  elif command -v podman-compose >/dev/null 2>&1; then echo "podman-compose"; \
  elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then echo "podman compose"; \
  fi)
MOCK := -f docker-compose.yml -f docker-compose.mock.yml
RUNTIME := $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)

.DEFAULT_GOAL := help

.PHONY: help demo up deploy down down-prod logs watch build test test-py clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@if [ -z "$(COMPOSE)" ]; then echo "  (no compose tool detected — run/down use raw podman via scripts/)"; fi

demo:  ## DEV stack on synthetic data — no API keys, never touches prod (http://localhost:5173)
	@[ -f .env ] || cp .env.example .env
	@if [ -n "$(COMPOSE)" ]; then \
	  echo ">> $(COMPOSE) $(MOCK) up --build"; \
	  $(COMPOSE) $(MOCK) up --build; \
	else \
	  echo ">> no compose tool — using scripts/run-stack.sh mock"; \
	  scripts/run-stack.sh mock; \
	fi

up:  ## DEV stack against REAL APIs (requires .env) — never touches prod
	@[ -f .env ] || { echo "ERROR: create .env from .env.example and add your API keys"; exit 1; }
	@if [ -n "$(COMPOSE)" ]; then \
	  echo ">> $(COMPOSE) up --build"; \
	  $(COMPOSE) up --build; \
	else \
	  echo ">> no compose tool — using scripts/run-stack.sh real"; \
	  scripts/run-stack.sh real; \
	fi

deploy:  ## Promote the CURRENT COMMIT to production (guardrailed — see scripts/deploy.sh)
	@scripts/deploy.sh

down:  ## Stop the DEV stack (production keeps running)
	@if [ -n "$(COMPOSE)" ]; then $(COMPOSE) $(MOCK) down; else scripts/stop-stack.sh dev; fi

down-prod:  ## Stop PRODUCTION (confirmation-gated)
	@scripts/stop-stack.sh prod

logs:  ## Tail logs from all services (compose) or print podman hint
	@if [ -n "$(COMPOSE)" ]; then $(COMPOSE) logs -f; \
	else echo "raw podman: podman logs -f ap-engine | ap-gateway | ap-rag | ap-pm | ap-mma | ap-dash"; fi

watch:  ## Tail BOTH live streams in the terminal — no browser needed (Ctrl+C to quit)
	@$(RUNTIME) run --rm --network host \
	  -v $(PWD)/scripts/watch-stream.py:/watch.py:z \
	  agentpredict-gateway:dev python /watch.py ws://localhost:8000/ws

build:  ## Build all images without starting them
	@if [ -n "$(COMPOSE)" ]; then $(COMPOSE) build; \
	else for s in engine gateway agents rag; do podman build -t agentpredict-$$s:dev -f $$s/Dockerfile . ; done; \
	  podman build -t agentpredict-dashboard:dev -f dashboard/Dockerfile.dev ./dashboard; fi

test: test-py  ## Run all available test suites

test-py:  ## Run the Python unit suites (agents, rag, gateway)
	PINECONE_API_KEY=fake GOOGLE_API_KEY=fake PINECONE_INDEX_NAME=agentpredict \
	  python -m pytest agents/tests/unit rag/tests/unit gateway/tests/unit -q

clean: down  ## Stop the stack (alias for down)
