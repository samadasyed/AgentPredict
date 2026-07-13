# RESEARCH/ — AgentPredict MMA research function

This folder is the home of the research function for AgentPredict MMA, run from the `saify` branch.

- **[MASTER_PROMPT.md](MASTER_PROMPT.md)** — the charter. Read it first; it defines the standing question, ground truth, operating rules, and boundaries. It is a charter, not a script — expert judgment may override its specifics when justified.
- **[BETS.md](BETS.md)** — the live research-bet tracker: at most 2–3 active bets at a time, each with hypothesis, cheapest decisive experiment, kill criterion, and status. Dead bets stay listed with autopsies.
- **[memos/](memos/)** — one short memo per research cycle (`YYYY-MM-DD-topic.md`): what was investigated, what the evidence showed, bet status changes, and one clear recommendation.

House rules apply everywhere here: `saify` branch only, ask before touching source code outside this folder, secrets never in files or logs, unit tests mock external services (`pytest -m api` for live tests).
