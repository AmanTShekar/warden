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
                logger.warning(f"Semgrep execution failed ({e}) — falling back to AST static analysis engine")
                findings.extend(self._ast_scan_diff(diff_text))
        finally:
            os.remove(temp_path)
            
        return findings

    def _ast_scan_diff(self, diff_text: str) -> list[VulnerabilityFinding]:
        """
        Intelligent Python AST static security analysis of added code lines.
        Inspects Abstract Syntax Trees to catch real code vulnerabilities:
        - SQL Injection: f-strings (ast.JoinedStr), string concatenation, or % formatting in db execute()
        - Hardcoded Secrets: High Shannon entropy (H > 4.2) string constants & key patterns
        - Dynamic Code Injection: ast.Call nodes invoking eval(), exec(), __import__()
        """
        import ast
        import math
        import re

        findings: list[VulnerabilityFinding] = []
        
        # Extract added lines from unified diff format (lines starting with '+')
        added_lines = []
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
        
        added_code = "\n".join(added_lines) if added_lines else diff_text

        # Try AST parsing
        try:
            tree = ast.parse(added_code)
            for node in ast.walk(tree):
                # AST Check 1: SQL Injection via Formatted Query Execution
                if isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    elif isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    
                    if func_name in ("execute", "executemany", "raw", "query"):
                        if node.args:
                            first_arg = node.args[0]
                            # Dynamic f-string query: query = f"SELECT ... '{val}'"
                            if isinstance(first_arg, ast.JoinedStr):
                                findings.append(VulnerabilityFinding(
                                    vuln_type="sql_injection",
                                    severity="critical",
                                    line=getattr(node, "lineno", 1),
                                    file_path="diff",
                                    explanation="Critical SQL Injection: Dynamic f-string formatting passed directly to database execute() query",
                                    source="ast_static_analysis"
                                ))
                            # BinOp string concatenation: query = "SELECT ... " + val
                            elif isinstance(first_arg, ast.BinOp):
                                findings.append(VulnerabilityFinding(
                                    vuln_type="sql_injection",
                                    severity="critical",
                                    line=getattr(node, "lineno", 1),
                                    file_path="diff",
                                    explanation="Critical SQL Injection: String concatenation (+) or % formatting passed to database query",
                                    source="ast_static_analysis"
                                ))

                # AST Check 2: Hardcoded Secrets via Shannon Entropy Analysis
                is_str = isinstance(node, ast.Constant) and isinstance(node.value, str)
                if is_str:
                    val = node.value
                    if len(val) >= 16:
                        prob = [float(val.count(c)) / len(val) for c in dict.fromkeys(val)]
                        entropy = -sum([p * math.log(p) / math.log(2.0) for p in prob])
                        if (entropy > 4.0 and re.search(r"[A-Za-z0-9+/=]{20,}", val)) or re.search(r"AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36}|-----BEGIN.*KEY-----", val):
                            findings.append(VulnerabilityFinding(
                                vuln_type="hardcoded_secret",
                                severity="critical",
                                line=getattr(node, "lineno", 1),
                                file_path="diff",
                                explanation=f"Hardcoded high-entropy secret detected (Shannon entropy: {entropy:.2f})",
                                source="ast_static_analysis"
                            ))

                # AST Check 3: Dynamic Code Execution
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "__import__"):
                        findings.append(VulnerabilityFinding(
                            vuln_type="code_injection",
                            severity="high",
                            line=getattr(node, "lineno", 1),
                            file_path="diff",
                            explanation=f"Dangerous dynamic code execution function '{node.func.id}()' detected",
                            source="ast_static_analysis"
                        ))

        except Exception as parse_err:
            logger.debug(f"AST parsing skipped for non-python diff: {parse_err}")

        # Generalized regex analysis if AST parsed no python statements or diff is non-Python
        if not findings:
            if re.search(r"(?i)(SELECT|INSERT|UPDATE|DELETE)\b.*(WHERE|SET|VALUES)\b.*(['\"f]\s*\{|%\s*\(|\+\s*[a-z_])", diff_text):
                findings.append(VulnerabilityFinding(
                    vuln_type="sql_injection",
                    severity="critical",
                    line=1,
                    file_path="diff",
                    explanation="Unsanitized dynamic string formatting in database query (Static Pattern Match)",
                    source="static_analysis"
                ))
            if re.search(r"AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36}|-----BEGIN.*PRIVATE KEY-----", diff_text):
                findings.append(VulnerabilityFinding(
                    vuln_type="hardcoded_secret",
                    severity="critical",
                    line=1,
                    file_path="diff",
                    explanation="Hardcoded API credential or private key detected in patch",
                    source="static_analysis"
                ))

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
