# Cycle 3 — Fight week arrived early; first real capture running (2026-07-14)

**Finding:** the next capture window opened four days before fight night. Gamma lists 23 fight-shaped UFC markets today: the full **UFC Fight Night Jul 18** card (Usman vs. Du Plessis main event, $118K volume and actively trading) *and* the **Jul 25 card already pre-listed at near-zero volume**. That second cohort is a research gift — we can record price paths from market birth, which no post-hoc `prices-history` pull fully reconstructs (CLOB fidelity floors at 5-minute points; our recorder gets 5-second points plus the emit/held decision at each tick).

**Action taken:** didn't wait for the stack. `RESEARCH/harness/capture_run.py` runs the **real** Polymarket agent with a null emitter — no engine/gateway/RAG, no API keys, identical API load to production. Verified live (4 polls → 23 markets, 69 sub-threshold ticks, all 23 week histories at 57 points), then left running detached (`nohup`, log at `research_capture/capture_run.log`).

Ops notes:
- Check it's alive: `pgrep -f capture_run.py` · stop: `pkill -f capture_run.py`
- Skim the take: `python RESEARCH/harness/report.py research_capture`
- Disk: ~67KB/first minute incl. one-time histories; steady state far less. Days of running is MBs.
- Survives this session but **not a reboot** — restart the same command if the machine restarts.

**What this capture will decide (by ~Jul 19):**
1. Pre-fight drift structure: how much movement happens below the 0.01 emit threshold (feeds threshold tuning and B-003's latency case).
2. Volume-vs-listing-age curves for the Jul 25 cohort (when do markets become informative?).
3. Fight-night microstructure on Jul 18 — *if* the machine stays on through the card.

**Still needed for the other half of the dataset:** RAG-side `cycle`/`skip` records require the real stack (engine + rag + working Pinecone key) — that's fight night with Samad's volume-mount merge ([proposal](../proposals/2026-07-13-capture-volume-mounts.md)) and a fresh Pinecone key. Without those we still get the price-path half; with them we get explanation traces to feed B-002's decisive experiment.

**Bet status:** B-001 → first real capture in progress. B-002 unchanged (harness ready, waiting on data). B-003 unchanged (backlog; this capture produces the baseline it needs).
