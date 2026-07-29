# Warden — Progress Tracker

**Last updated:** July 28, 2026, 10:50 PM IST
**Deadline:** Aug 6, 2026, 11:59 PM IST
**Days remaining:** 9

---

## Sprint Status

### 🔲 Sprint 0 — Scaffold + Architecture (Jul 28 evening)
- [x] Project structure created
- [x] `pyproject.toml` with metadata
- [x] `.gitignore` (Python + GGUF + ROCm)
- [x] MIT `LICENSE`
- [x] `requirements.txt`
- [x] Core data models (`warden/tiers/base.py`) — CheckResult, ScanResult, RoutingResult, SecurityEvent
- [x] Central config (`warden/config.py`) — TrustLevel, Decision, ContentSource enums + dataclass configs
- [x] Tier 0 regex checker — **FULLY IMPLEMENTED** with injection, secret, SQLi, shell patterns
- [x] Tier 1 classifier skeleton — HuggingFace transformers loader (not pytector)
- [x] Tier 2 LLM skeleton — llama-cpp-python with structured prompts
- [x] Routing engine (`ThrottleRouter`) — full cascade with graceful degradation
- [-] Trust classifier (Descoped)
- [x] Policy engine — YAML loader + rule evaluation + shadow mode
- [x] Diff guard skeleton — Semgrep integration
- [x] CaMeL interpreter — quarantine_content, plan_with_refs, check_tool_call
- [x] Audit log — full SQLite schema + event logging + known-blocked/safe queries
- [x] RAG retriever — ChromaDB integration with pattern storage and retrieval
- [x] CLI with Rich output — `warden check` and `warden stats` commands
- [x] Default security policy (`policies/default.yaml`)
- [x] Attack samples (50 generated)
- [x] Test suite — Tier 0 tests (injections, secrets, benign, latency) + routing tests
- [x] Cloud GPU setup script (`scripts/setup_cloud.sh`)
- [x] README rewritten as proper project README
- [x] GPU validation on Radeon Cloud — **NEXT**
- [x] Dockerfile
- [x] Initial git commit + push

### ✅ Sprint 1 — Tier 0 + Tier 1 + Attack Samples (Jul 29 AM)
- [x] Expand attack samples (sophisticated injections, vulnerable diffs)
- [x] Platt scaling / confidence calibration for Tier 1
- [x] Test Tier 1 with actual Prompt Guard 2 model
- [x] Full test coverage for Tier 0 against all attack_samples/*.txt

### 🔲 Sprint 2 — Tier 2 + Diff Guard (Partially Complete)
- [x] Implement Semgrep integration in DiffGuard
- [x] Test Tier 2 with mock LLM (and AMD TokenFactory fallback)
- [x] Create vulnerable diff samples (IDOR, SQLi, XSS patches)
- [x] DiffGuard test suite
- [x] Local ROCm acceleration (llama_cpp flash_attn, n_batch)

### ✅ Sprint 3 — RAG + Memory (Jul 30 AM)
- [x] Populate RAG with OWASP LLM Top 10 patterns
- [x] Pattern tracker (repeat-offender detection and memory block loop)
- [x] Feedback loop (learn from user overrides)
- [x] Memory tests (`test_router_memory.py`)

### ✅ Sprint 4 — Policy + CaMeL (Jul 30 PM) — *CaMeL descoped, see Sprint 0 Known Gaps*
- [x] Policy test suite (`test_policy.py`)
- [x] CaMeL capability tracker (`check_tool_call`) + tests (`test_camel.py`)
- [x] **CaMeL GO/NO-GO decision gate** → GO for capability tracker, NO-GO for dual-LLM split (now descoped)
- [x] Phase 1 checkpoint: all tests green

### ✅ Sprint 5 — Routing Engine (Jul 31)
- [x] Batch scheduler (`batch_scheduler.py` thread safety)
- [x] Confidence calibrator
- [x] Full routing test suite (`test_routing.py`)
- [x] Routing stats reporting (`gpu_utilization_pct`, etc)

### ✅ Sprint 6 — Orchestrator + Integration (Jul 31 AM)
- [x] LangChain orchestrator (WardenOrchestrator)
- [x] CLI entry points (`warden check`, `warden stats`)
- [x] Shadow mode end-to-end

### ✅ Sprint 7 — Dashboard (Aug 1–2)
- [x] Gradio dashboard (5 tabs)
- [x] Live stats + integration demo
- [x] demo_final.sh / proof pipeline

### 🔲 Sprint 8 — GPU Integration (Aug 2)
- [ ] Full GPU inference with Qwen2.5-Coder on Radeon Cloud (Needs Cloud Run)
- [x] Integration with ROCm llama-cpp-python
- [x] Telemetry pipeline (benchmarking script)

### 🔲 Sprint 9 — Benchmarks (Aug 3)
- [ ] Full benchmark suite (3 scenarios)
- [ ] Headline metric computed
- [ ] Quantization comparison table
- [ ] Raw evidence committed

### 🔲 Sprint 10 — Demo + Spec Doc (Aug 4)
- [ ] Demo video recorded
- [ ] Project specification document

### 🔲 Sprint 11 — Polish (Aug 5)
- [ ] README finalized
- [ ] PPT/poster
- [ ] Final test pass

### 🔲 Sprint 12 — Submit (Aug 6)
- [ ] Luma submission
- [ ] All links verified

---

## Known Gaps

Tracked honestly so judges can see what's tested vs. what's claimed. Updated as
of July 28, 2026.

### Architecture / Routing
- **P-LLM / Q-LLM split OFFICIALLY DESCOPED.** The dual-LLM
  privileged-quarantined-LLM architecture described in `plan.md`
  was prototyped but never wired into the router cascade. As of
  this session, the dead code (`quarantine_content`, `plan_with_refs`,
  `LabeledRef`, `EXTRACT_ONLY` enum) was removed. The data-flow
  capability tracker (`CaMeLInterpreter.check_tool_call`) is the
  shipped subset and is wired into `WardenOrchestrator.guard_tool_call`.
  The router's phantom "Trusted User Input → routing to P-LLM" auto-allow
  was reframed honestly as a user-direct fast-path (saves Tier 1/2
  latency when Tier 0 passes — the real reason it existed).
  `enable_camel` flag flipped to `False`; CaMeL capability tracker still
  works via the orchestrator, not the descoped dual-LLM path.
- **Cross-process sweep not implemented.** `PatternTracker` auto-block
  works in-process; audit-log `is_known_blocked` is queried per-router
  instance but a true background sweeper daemon is not yet wired.

### CI / Validation
- **No AMD GPU locally.** All ROCm optimizations (KV cache Q8, adaptive
  offload, flash-attn, physical-core thread pinning) are code-complete but
  unvalidated against `rocm-smi` telemetry. `measure_power.py` is the harness;
  needs a cloud run.

### Benchmark Credibility
- **SHA-256 manifest implemented** (`scripts/sha256_manifest.py`) — 104
  entries across scripts/policies/data/tests. Model GGUFs excluded by
  default (`--include-models` to include). Manifest committed at
  `benchmarks/results/manifest.jsonl`.
- **`measure_power.py` rewritten** as a real harness: rocm-smi JSON
  polling, joules = avg_watts × duration_s, CSV + summary, graceful
  degradation on non-ROCm hosts. Tested on dev (4 tests) but not yet run
  on actual GPU.


