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
- [x] Trust classifier
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
- [ ] GPU validation on Radeon Cloud — **NEXT**
- [ ] Dockerfile
- [ ] Initial git commit + push

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

### ✅ Sprint 4 — Policy + CaMeL (Jul 30 PM)
- [x] Policy test suite (`test_policy.py`)
- [x] CaMeL end-to-end test (`test_camel.py`)
- [x] **CaMeL GO/NO-GO decision gate**
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
- [ ] Full GPU inference with Qwen2.5-Coder on Radeon Cloud
- [ ] Benchmark framework (power, latency, accuracy)

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

- [ ] All links verified
