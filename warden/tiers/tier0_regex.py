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
from dataclasses import dataclass, field
from typing import Optional

from warden.config import Decision
from warden.tiers.base import CheckResult, TierChecker


# --- Pattern Definitions ---

# Known injection prefixes (case-insensitive)
INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("instruction_override", re.compile(
        r"ignore\s+(all\s+)?previous\s+instructions",
        re.IGNORECASE
    )),
    ("instruction_override", re.compile(
        r"disregard\s+(all\s+)?(prior|previous|above)\s+(instructions|rules|guidelines)",
        re.IGNORECASE
    )),
    ("system_prompt_injection", re.compile(
        r"^(SYSTEM|ADMIN|ROOT)\s*:\s*",
        re.IGNORECASE | re.MULTILINE
    )),
    ("role_hijack", re.compile(
        r"you\s+are\s+now\s+(a|an|the)\s+",
        re.IGNORECASE
    )),
    ("role_hijack", re.compile(
        r"pretend\s+(you\s+are|to\s+be)\s+",
        re.IGNORECASE
    )),
    ("jailbreak", re.compile(
        r"(DAN|do\s+anything\s+now|developer\s+mode|jailbreak)",
        re.IGNORECASE
    )),
    ("tool_injection", re.compile(
        r"(call|execute|run|invoke)\s+(write_file|delete_file|rm\s|curl\s|wget\s)",
        re.IGNORECASE
    )),
    ("encoded_payload", re.compile(
        r"(eval|exec|import\s+os|subprocess|__import__)\s*\(",
        re.IGNORECASE
    )),
]

# Secret patterns
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aws_access_key", re.compile(r"AKIA[A-Z0-9]{16}")),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github_token_old", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("private_key", re.compile(r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)?\s*PRIVATE\s+KEY-----")),
    ("jwt_token", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("generic_api_key", re.compile(r"(?i)(api[_-]?key|apikey|api[_-]?secret)\s*[=:]\s*['\"][A-Za-z0-9]{20,}['\"]")),
]

# SQL injection markers
SQLI_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("sql_injection", re.compile(
        r"('\s*(OR|AND)\s+['\d]|;\s*(DROP|DELETE|UPDATE|INSERT|UNION)\s)",
        re.IGNORECASE
    )),
    ("sql_injection", re.compile(
        r"(UNION\s+SELECT|INTO\s+OUTFILE|LOAD_FILE)",
        re.IGNORECASE
    )),
]

# Dangerous shell commands
SHELL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("dangerous_command", re.compile(r"rm\s+-rf\s+/", re.IGNORECASE)),
    ("dangerous_command", re.compile(r"curl\s+.*\|\s*(ba)?sh", re.IGNORECASE)),
    ("dangerous_command", re.compile(r"chmod\s+777\s+", re.IGNORECASE)),
    ("dangerous_command", re.compile(r"wget\s+.*-O\s*-\s*\|\s*(ba)?sh", re.IGNORECASE)),
]

# Base64 detection (potential hidden payloads)
BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")

ALL_PATTERNS: list[tuple[str, re.Pattern]] = (
    INJECTION_PATTERNS
    + SECRET_PATTERNS
    + SQLI_PATTERNS
    + SHELL_PATTERNS
)


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

        matched: list[str] = []
        matched_weights: list[float] = []

        # Run all pattern groups
        for pattern_name, pattern in ALL_PATTERNS:
            if pattern.search(text):
                matched.append(pattern_name)
                matched_weights.append(self._pattern_weight(pattern_name))

        # Check for suspicious base64 blocks
        b64_matches = BASE64_PATTERN.findall(text)
        if any(len(m) > 100 for m in b64_matches):
            matched.append("suspicious_base64")
            matched_weights.append(0.4)

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

    def _pattern_weight(self, pattern_name: str) -> float:
        """Assign threat weight based on pattern type."""
        weights = {
            "instruction_override": 0.9,
            "system_prompt_injection": 0.85,
            "role_hijack": 0.7,
            "jailbreak": 0.8,
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
        return weights.get(pattern_name, 0.5)

    def _build_explanation(self, matched: list[str], decision: Decision) -> str:
        if not matched:
            return "No suspicious patterns detected."
        patterns_str = ", ".join(set(matched))
        return f"Tier 0 matched: [{patterns_str}] → {decision.value}"
