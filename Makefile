# AgentPredict — common dev/run targets.
#
# COMPOSE defaults to "docker compose"; override for podman:
#   make demo COMPOSE="podman compose"
COMPOSE ?= docker compose
MOCK    := -f docker-compose.yml -f docker-compose.mock.yml

.DEFAULT_GOAL := help

.PHONY: help demo up down logs build test test-py clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

demo:  ## Run the WHOLE stack on synthetic data — no API keys (dashboard: http://localhost:5173)
	@[ -f .env ] || cp .env.example .env
	$(COMPOSE) $(MOCK) up --build

up:  ## Run the stack against REAL APIs (requires a populated .env — see `make help`)
	@[ -f .env ] || { echo "ERROR: create .env from .env.example and add your API keys"; exit 1; }
	$(COMPOSE) up --build

down:  ## Stop and remove all containers
	-$(COMPOSE) $(MOCK) down

logs:  ## Tail logs from all services
	$(COMPOSE) logs -f

build:  ## Build all images without starting them
	$(COMPOSE) build

test: test-py  ## Run all available test suites

test-py:  ## Run the Python unit suites (agents, rag, gateway)
	PINECONE_API_KEY=fake GOOGLE_API_KEY=fake PINECONE_INDEX_NAME=agentpredict \
	  python -m pytest agents/tests/unit rag/tests/unit gateway/tests/unit -q

clean:  ## Remove containers, default network, and dangling build cache
	-$(COMPOSE) $(MOCK) down --remove-orphans
