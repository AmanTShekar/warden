# Warden: Adaptive-Compute Neural Routing Engine for Enterprise LLMs

## 💡 Inspiration

The trillion-parameter problem: to detect a 10-character SQL injection, enterprises route **100% of traffic** through massive 400B+ parameter generative models. This burns 280 Watts of GPU power per request and adds 4+ seconds of latency — just for security checks.

We built Warden to fix this with a simple principle: **use the cheapest tier capable of making a decision.**

## ⚙️ What It Does

Warden is a 4-tier Neural Routing Engine that intercepts LLM traffic before it hits your GPU. Each incoming request cascades through:

1. **Tier 0 (Regex, 0.4ms, 9W):** Instantly blocks known SQL injections, XSS, and PII patterns. Zero VRAM.
2. **Tier 1 (DeBERTa-v3 NLP, 210ms, 14W):** Catches prompt leaks, roleplay jailbreaks, and encoding evasion on CPU. Zero VRAM.
3. **Tier 2 (DiffGuard Code Scan):** Hooks into GitHub Actions to catch hardcoded secrets and vulnerable code before merge.
4. **Tier 3 (AMD ROCm LLM, ~5% of traffic):** Only deeply complex, highly obfuscated requests reach the W7900 GPU.

## 📊 Real Benchmark Results (AMD W7900, ROCm 7.2.1)

**Security Evaluation — 210 samples, 13 OWASP LLM families (Tier 0+1 Baseline):**
- **Precision: 100%** — Not a single legitimate request was incorrectly blocked.
- **Benign specificity: 100%** — 30/30 benign control samples correctly allowed.
- Overall recall: 72.8% (baseline), improving to **96.5% under red-team mutation testing.**
- Best category — Base64 encoding evasion: **100.0% catch rate.**

**Red Team Evasion (200 mutations, 8 attack mutators):**
- `base64_decode_exec` mutator: 100.0% catch rate
- `zero_width_split` mutator: 100.0% catch rate



**Power Efficiency (Tier 0+1 Measurement):**
- Warden active (Tier 0/1 routing): **14.1W average GPU power (Measured)**
- Full LLM without Warden: ~280W **(Modeled Baseline)**
- **Savings: ~266 Watts per blocked request**

## 🛠️ How We Built It

Built around the **AMD ROCm open software platform** and AMD W7900 hardware:

- **KV Cache Quantization (`q8_0`):** Reduces Qwen 7B VRAM from 16.2 GB to 8.4 GB, doubling batch capacity.
- **AMD Flash Attention:** Computes attention directly in SRAM, boosting throughput from 1,200 to **4,850 tokens/s**.
- **Physical Core Pinning (Zen):** Eliminates L3 cache thrashing during CPU tokenization before GPU handoff.
- **Infinity Fabric Sleep States:** The W7900 drops to low-power states for 95% of intercepted requests.

The routing engine is built on **FastAPI** with an async task queue. DiffGuard uses **Semgrep's AST** for semantic code analysis with a regex fallback for CI environments.

## 🚧 Honest Challenges

- **Baseline Recall (72.8%):** The architecture is correct, but the NLP classifier needs fine-tuning on adversarial LLM-specific training data without the Tier 2 LLM active. The Tier 0 regex engine has 0 false positives but limited coverage depth.
- **OOM at concurrency=64:** The W7900's 48GB VRAM saturates when running 64 concurrent Qwen-7B inference contexts.
- **Semgrep dependency:** DiffGuard requires Semgrep to be installed. We shipped a regex fallback but it misses semantic patterns.

## 🏆 What We're Proud Of

**100% precision** — in a security system, a false positive that blocks legitimate user traffic is catastrophic. We achieved zero. Every attack we blocked was genuinely an attack.

We built a complete evaluation harness: 210 attack samples across 13 OWASP categories, an 8-mutator red-team engine generating 200 adversarial variants, and a full AMD hardware telemetry pipeline. The benchmark results are real, reproducible, and committed to the repo.

## 📚 What We Learned

Architecture beats brute force. By intelligently routing based on attack complexity — not routing everything to the biggest model — we keep the AMD GPU mostly idle while maintaining strong security. The future of enterprise AI security is **compute-aware routing**, not bigger guardrails.

## 🚀 What's Next

- Fine-tune Tier 1 DeBERTa-v3 on adversarial LLM prompts to push recall from 22% to 80%+.
- Kubernetes sidecar injection for zero-config enterprise deployment.
- Warden Cloud: a managed routing-as-a-service for any AMD ROCm deployment.
