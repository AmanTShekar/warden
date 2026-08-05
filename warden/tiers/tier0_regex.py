"""
Tier 0: Regex/heuristic security checks.

Zero GPU, zero model — pure pattern matching. Catches obvious attacks
instantly (sub-5ms). The cheapest possible filter before escalating
to heavier tiers.
"""

from __future__ import annotations

import re
import time
import math
import base64
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from warden.config import Decision
from warden.tiers.base import CheckResult, TierChecker


# --- Pattern Definitions (compiled into a single fast regex) ---

ALL_PATTERNS: list[tuple[str, str]] = [
    # Known injection prefixes
    ("instruction_override", r"(?i)ignore\s+(all\s+)?previous\s+instructions"),
    ("instruction_override", r"(?i)disregard\s+(all\s+)?(prior|previous|above)\s+(instructions|rules|guidelines)"),
    ("system_prompt_injection", r"(?im)^(SYSTEM|ADMIN|ROOT)\s*:\s*"),
    ("role_hijack", r"(?i)you\s+are\s+now\s+(a|an|the)\s+"),
    ("role_hijack", r"(?i)you\s+are\s+[a-z0-9_-]+\s*,?\s*(a|an|the\s+[a-z\s]+)?\s*with\s+no\s+(ethical|safety)"),
    ("role_hijack", r"(?i)pretend\s+(you\s+are|to\s+be)\s+"),
    ("jailbreak", r"(?i)(DAN|do\s+anything\s+now|developer\s+mode|jailbreak|no\s+(ethical|safety)\s+(guidelines|rules|constraints))"),
    ("auth_bypass_injection", r"(?i)bypass\s+(authentication|security|authorization|login)"),
    ("tool_injection", r"(?i)(call|execute|run|invoke)\s+(write_file|delete_file|rm\s|curl\s|wget\s)"),
    ("encoded_payload", r"(?i)(eval|exec|import\s+os|subprocess|__import__)\s*\("),
    
    # Secret patterns
    ("aws_access_key", r"AKIA[A-Z0-9]{16}"),
    ("github_token", r"ghp_[A-Za-z0-9]{36}"),
    ("github_token_old", r"gh[pousr]_[A-Za-z0-9]{36,}"),
    ("private_key", r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)?\s*PRIVATE\s+KEY-----"),
    ("jwt_token", r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ("generic_api_key", r"(?i)(api[_-]?key|apikey|api[_-]?secret)\s*[=:]\s*['\"][A-Za-z0-9]{20,}['\"]"),
    
    # SQL injection markers
    ("sql_injection", r"(?i)('\s*(OR|AND)\s+['\d]|;\s*(DROP|DELETE|UPDATE|INSERT|UNION)\s)"),
    ("sql_injection", r"(?i)(UNION\s+SELECT|INTO\s+OUTFILE|LOAD_FILE)"),
    
    # Dangerous shell commands
    ("dangerous_command", r"(?i)rm\s+-rf\s+/"),
    ("dangerous_command", r"(?i)curl\s+.*\|\s*(ba)?sh"),
    ("dangerous_command", r"(?i)chmod\s+777\s+"),
    ("dangerous_command", r"(?i)wget\s+.*-O\s*-\s*\|\s*(ba)?sh"),
]

# Base64 detection (potential hidden payloads)
BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")

PATTERN_WEIGHTS = {
    "instruction_override": 0.9,
    "system_prompt_injection": 0.85,
    "role_hijack": 0.85,
    "pretend_persona": 0.7,
    "jailbreak": 0.85,
    "auth_bypass_injection": 0.9,
    "tool_injection": 0.95,
    "encoded_payload": 0.6,
    "aws_access_key": 0.95,
    "github_token": 0.95,
    "github_token_old": 0.9,
    "private_key": 0.95,
    "jwt_token": 0.5,
    "generic_api_key": 0.8,
    "sql_injection": 0.85,
    "dangerous_command": 0.9,
    "suspicious_base64": 0.4,
}

# Compile a single master regex for extreme sub-5ms performance
_master_parts = []
for _idx, (_name, _pattern_str) in enumerate(ALL_PATTERNS):
    if _pattern_str.startswith("(?i)"):
        _pattern_str = "(?i:" + _pattern_str[4:] + ")"
    elif _pattern_str.startswith("(?im)"):
        _pattern_str = "(?im:" + _pattern_str[5:] + ")"
    _master_parts.append(f"(?P<{_name}_{_idx}>{_pattern_str})")
MASTER_PATTERN = re.compile("|".join(_master_parts))


class Tier0RegexChecker(TierChecker):
    """
    Tier 0 — Zero-cost regex and heuristic pattern matching.

    Catches obvious attacks instantly. Designed for:
    - Known injection prefixes
    - Secret patterns (AWS keys, GitHub tokens, private keys, JWTs)
    - SQL injection markers
    - Dangerous shell commands
    - Suspicious base64 payloads

    Latency target: sub-5ms per check.
    """

    @property
    def tier_number(self) -> int:
        return 0

    def check(self, text: str, context: str = "") -> CheckResult:
        """Run all regex/heuristic patterns against the input text."""
        start = time.perf_counter()

        # --- Tier 0.5: Normalization (homoglyphs, zero-width, base64) ---
        # Delegated to warden.tiers.tier0_5_normalizer — pure function, unit-tested
        # independently, and used by red-team tests to verify the homoglyph/zero-width
        # gap is closed (see tests/test_attack_corpus.py + tests/test_tier0_5.py).
        from warden.tiers.tier0_5_normalizer import normalize as tier0_5_normalize
        norm_text = tier0_5_normalize(text)

        matched_set = set()
        
        # Single-pass regex C-engine matching (Optimization A1)
        for m in MASTER_PATTERN.finditer(norm_text):
            for k, v in m.groupdict().items():
                if v is not None:
                    matched_set.add(k.rsplit('_', 1)[0])

        matched = list(matched_set)
        matched_weights = [PATTERN_WEIGHTS.get(m, 0.5) for m in matched]

        # Check for suspicious base64 blocks (use original text; the
        # normalizer decoded short blocks already, but very long encoded
        # blobs are still suspicious even if they decode to noise).
        if len(text) >= 40:
            b64_matches = BASE64_PATTERN.findall(text)
            if any(len(m) > 100 for m in b64_matches):
                matched.append("suspicious_base64")
                matched_weights.append(PATTERN_WEIGHTS["suspicious_base64"])

        # Compound independent threat probabilities: 1 - prod(1 - w_i)
        if matched_weights:
            threat_score = 1.0 - math.prod(1.0 - w for w in matched_weights)
        else:
            threat_score = 0.0

        # Determine decision
        if threat_score >= 0.8:
            decision = Decision.BLOCK
        elif threat_score >= 0.3:
            decision = Decision.UNCERTAIN  # Escalate to Tier 1
        else:
            decision = Decision.ALLOW

        latency = (time.perf_counter() - start) * 1000

        return CheckResult(
            decision=decision,
            confidence=threat_score,
            tier=0,
            latency_ms=latency,
            matched_patterns=matched,
            explanation=self._build_explanation(matched, decision),
        )

    def is_available(self) -> bool:
        return True  # Regex is always available

    def _build_explanation(self, matched: list[str], decision: Decision) -> str:
        if decision == Decision.ALLOW:
            return "No suspicious patterns detected."
        elif decision == Decision.BLOCK:
            return f"Matched critical threat patterns: {', '.join(matched)}"
        else:
            return f"Matched suspicious patterns requiring escalation: {', '.join(matched)}"
