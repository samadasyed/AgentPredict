# Cycle 2 — Eval harness v0 built; capture armed; one infra gap (2026-07-13)

**Question:** With B-001's recorder shipped, what must be true before the next card lists so its fight week isn't wasted? Answer: capture must run where the stack runs, and the scoring side (B-002) must exist so the first capture is immediately analyzable. Both addressed this cycle; one piece needs Samad.

## Done

1. **Capture armed locally.** `RESEARCH_CAPTURE=1` + `RESEARCH_CAPTURE_DIR` now set in `.env` (values only — no secrets touched). Verified the flag propagates into containers via compose `env_file:` and `run-stack.sh --env-file .env`.
2. **Infra gap found: captures die with containers.** Neither `docker-compose.yml` nor `run-stack.sh` mounts a volume for the agent/rag containers — anything written inside dies on container removal (= every deploy). Exact two-line fix written up as a proposal to Samad: [proposals/2026-07-13-capture-volume-mounts.md](../proposals/2026-07-13-capture-volume-mounts.md). Until merged, only non-containerized runs persist captures.
3. **B-002 harness v0 shipped** (`RESEARCH/harness/`, stdlib-only, fully offline):
   - `harness.py` — loads capture dirs; per-cycle **grounding** (proper-noun + numeric claims traced to trigger/context/evidence, with percent↔fraction normalization so "65%" grounds against 0.65), **timeliness** (pipeline latency + tick→explanation e2e), **outcome consistency** (continued/reverted/flat from the captured price path, 10-min window — a feature, not a verdict), and the **PASS/FAIL separation** stat that is B-002's kill criterion.
   - `report.py` — CLI: `python RESEARCH/harness/report.py [capture_dir]`.
   - `test_harness.py` — 5 offline tests (run explicitly: `pytest RESEARCH/harness/test_harness.py`; kept off pytest's default testpaths deliberately — research tooling shouldn't gate the product suites).
4. **Full loop smoke-tested:** mock-mode stack components → real capture files → harness report. Output sane: mock explanation scored grounding 1.000 (it only restates trigger facts — correct); a planted hallucination ("Khabib Nurmagomedov landed 47 takedowns") scores low with the fabricated name and number itemized as ungrounded claims.

## Honest limits of v0 (known, acceptable until real data)

- Grounding checks **entities and numbers**, not causal claims ("because of the knockdown" is only checked via its nouns). Good hallucination tripwire; not a full factuality judge. An LLM-judge pass can be layered later **if** real captures show entity-grounding saturating at 1.0 while quality still varies.
- Outcome consistency is descriptive. Markets revert for good reasons; "reverted" ≠ "explanation wrong." It becomes decision-grade only with volume.
- The kill-criterion check (PASS/FAIL separation) needs real verifier FAILs — mock mode barely produces them. First real card decides.

## Bet status

- **B-001:** built + armed locally; **blocked on Samad's volume-mount merge for prod capture**. First real capture = next card's fight week.
- **B-002:** harness v0 shipped and smoke-tested; waiting on first real capture to run the decisive experiment (PASS/FAIL separation on real cycles).
- **B-003:** still backlogged, unchanged.

## Recommendation

Ping Samad on the volume-mount proposal **before the next card lists** (days, not weeks — UFC 329's markets are already gone and the next batch appears fight week). Everything else is in place: the first real fight night now produces a scored, persistent dataset with zero additional work.
