# Warden Architecture & System Specification

## Overview

Warden is an adaptive-compute security engine for enterprise Large Language Model (LLM) deployments.
Rather than routing 100% of user prompts to a massive 400B+ parameter generative model on high-TDP GPUs, Warden introduces a **5-tier cascading evaluation topology**.

Each incoming request is evaluated sequentially against increasingly capable, higher-compute defense layers. The process halts at the **cheapest tier capable of making a security decision**.

---

## Evaluation Cascades

`
[ User Prompt / Input ]
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Tier 0: Deterministic Regex Engine (CPU)              │
│ Latency: ~0.4ms  |  VRAM: 0 MB  |  Power: 9.0W         │
│ Scope: SQLi, XSS, PII, Shell injection, Known CVEs     │
└──────────────────────────┬─────────────────────────────┘
                           │ Pass / Uncertain
                           ▼
┌────────────────────────────────────────────────────────┐
│ Tier 0.5: Normalizer & Encoding Pass (CPU)            │
│ Latency: ~0.2ms  |  VRAM: 0 MB  |  Power: 9.2W         │
│ Scope: Base64 decoding, Homoglyph swap, Zero-width    │
└──────────────────────────┬─────────────────────────────┘
                           │ Decoded text
                           ▼
┌────────────────────────────────────────────────────────┐
│ Tier 1: DeBERTa-v3 NLP Classifier (CPU/NPU)           │
│ Latency: ~210ms  |  VRAM: 0 MB  |  Power: 14.1W        │
│ Scope: Roleplay jailbreaks, Prompt leaks, Suffix attacks│
└──────────────────────────┬─────────────────────────────┘
                           │ Confidence < Threshold
                           ▼
┌────────────────────────────────────────────────────────┐
│ Tier 2: DiffGuard & CaMeL Tool Interceptor            │
│ Scope: Code PR AST diff scan, Tool call parameters    │
└──────────────────────────┬─────────────────────────────┘
                           │ Unresolved (~5% of traffic)
                           ▼
┌────────────────────────────────────────────────────────┐
│ Tier 3: AMD ROCm LLM (AMD W7900 — 48GB VRAM)           │
│ Latency: ~1200ms |  VRAM: 8.4 GB (q8_0) | Power: 240W  │
│ Scope: Deep semantic analysis & complex context        │
└────────────────────────────────────────────────────────┘
`

---

## Component Breakdown

1. **warden/orchestrator.py**: Central coordinator that executes the tier cascade, logs audit events, and interfaces with the policy engine.
2. **warden/tiers/**:
   - 	ier0_regex.py: Compiled pattern matcher for high-confidence deterministic threats.
   - 	ier0_5_normalizer.py: Text preprocessor that unpacks obfuscations (Base64, homoglyphs, zero-width characters) before downstream NLP analysis.
   - 	ier1_classifier.py: HuggingFace DeBERTa-v3 model wrapper evaluating semantic intent.
   - 	ier2_llm.py: AMD ROCm-accelerated LLM pipeline utilizing q8_0 KV cache quantization and AMD Flash Attention.
3. **warden/guards/**:
   - diff_guard.py: Static analysis AST scanner for code diffs in CI/CD pipelines.
   - policy.py: YAML-based Policy-as-Code evaluator supporting declarative security rules.
4. **warden/camel/**:
   - interpreter.py: Interceptor for LLM tool call payloads, enforcing quarantine and verification rules.
5. **warden/memory/**:
   - udit_log.py: SQLite-backed immutable decision logger.
   - pattern_tracker.py: Tracks threat frequencies and routing telemetry across tiers.

---

## Memory & Caching Architecture

- **Exact Match Shortcut**: Safe queries and previously blocked signatures are cached in memory for sub-millisecond shortcut decisions.
- **Audit Persistence**: Every security decision (decision, explanation, latency, tier, timestamp) is logged asynchronously into warden_audit.db.
