"""
Diff Guard — Semgrep + LLM escalation for code vulnerability scanning.

Scans AI-generated code diffs before commit for the blind spots
AI-generated code is statistically prone to: missing auth checks,
hardcoded secrets, missing tenant boundaries.
"""

from __future__ import annotations

import logging
import subprocess
import json
import time
from typing import Optional

from warden.tiers.base import ScanResult, VulnerabilityFinding
from warden.tiers.tier2_llm import Tier2LLM

logger = logging.getLogger(__name__)


class DiffGuard:
    """
    Scans code diffs for security vulnerabilities.

    Pipeline:
    1. Run Semgrep (deterministic, fast) on the diff
    2. If Semgrep finds nothing but diff is large/complex → escalate to LLM
    3. Merge results from both sources
    """

    def __init__(
        self,
        llm_tier: Optional[Tier2LLM] = None,
        semgrep_rules: str = "p/owasp-top-ten",
        escalation_threshold: int = 5,  # Lines of diff to trigger LLM escalation
    ):
        self.llm_tier = llm_tier
        self.semgrep_rules = semgrep_rules
        self.escalation_threshold = escalation_threshold

    def scan_diff(self, diff_text: str) -> ScanResult:
        """
        Scan a code diff for vulnerabilities.

        1. Run Semgrep (fast, deterministic)
        2. If Semgrep finds nothing AND diff is complex → escalate to LLM
        3. Merge results
        """
        start = time.perf_counter()
        findings: list[VulnerabilityFinding] = []
        scanner_used = "none"
        diff_lines = len(diff_text.splitlines())

        # Step 1: Semgrep scan
        semgrep_findings = self._run_semgrep(diff_text)
        if semgrep_findings:
            findings.extend(semgrep_findings)
            scanner_used = "semgrep"

        # Step 2: LLM escalation (if Semgrep found nothing and diff is complex)
        if not semgrep_findings and diff_lines >= self.escalation_threshold:
            if self.llm_tier and self.llm_tier.is_available():
                llm_findings = self._run_llm_scan(diff_text)
                if llm_findings:
                    findings.extend(llm_findings)
                    scanner_used = "both" if scanner_used == "semgrep" else "llm"

        latency = (time.perf_counter() - start) * 1000

        return ScanResult(
            vulnerabilities=findings,
            latency_ms=latency,
            scanner=scanner_used,
            diff_size_lines=diff_lines,
        )

    def _run_semgrep(self, diff_text: str) -> list[VulnerabilityFinding]:
        """Run Semgrep on the diff text. Returns findings or empty list."""
        import tempfile
        import subprocess
        import json
        import os

        findings = []
        # Create a temporary file to hold the diff/code
        fd, temp_path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(diff_text)
            
            # Run semgrep scan
            cmd = ["semgrep", "scan", "--json", "--config=p/python", temp_path]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.stdout:
                    data = json.loads(result.stdout)
                    for match in data.get("results", []):
                        findings.append(VulnerabilityFinding(
                            vuln_type=match.get("check_id", "unknown"),
                            severity=match.get("extra", {}).get("severity", "medium").lower(),
                            line=match.get("start", {}).get("line"),
                            file_path=match.get("path", ""),
                            explanation=match.get("extra", {}).get("message", "Semgrep finding"),
                            source="semgrep"
                        ))
            except Exception as e:
                logger.warning(f"Semgrep execution failed: {e}")
        finally:
            os.remove(temp_path)
            
        return findings

    def _run_llm_scan(self, diff_text: str) -> list[VulnerabilityFinding]:
        """Escalate to LLM for semantic code analysis."""
        if not self.llm_tier:
            return []

        result = self.llm_tier.check_code(diff_text)

        findings = []
        if result.raw_output and isinstance(result.raw_output, dict):
            for vuln in result.raw_output.get("vulnerabilities", []):
                findings.append(VulnerabilityFinding(
                    vuln_type=vuln.get("type", "unknown"),
                    severity=vuln.get("severity", "medium"),
                    line=vuln.get("line", 0),
                    explanation=vuln.get("explanation", ""),
                    source="llm",
                ))

        return findings
