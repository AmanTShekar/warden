import pytest
from unittest.mock import patch, MagicMock
import json

from warden.guards.diff_guard import DiffGuard
from warden.tiers.base import VulnerabilityFinding


def test_diff_guard_semgrep_hit():
    """Test that DiffGuard successfully parses a Semgrep JSON output."""
    guard = DiffGuard(llm_tier=None)
    
    # Mock Semgrep subprocess output
    mock_semgrep_output = {
        "results": [
            {
                "check_id": "python.lang.security.audit.exec-use.exec-use",
                "path": "test.py",
                "start": {"line": 10},
                "extra": {
                    "message": "Use of exec detected.",
                    "severity": "HIGH",
                    "metadata": {
                        "cwe": "CWE-94"
                    }
                }
            }
        ]
    }
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(mock_semgrep_output)
        mock_run.return_value = mock_result
        
        scan_result = guard.scan_diff("def test():\n    exec('print(1)')")
        
        assert scan_result.has_findings is True
        assert scan_result.scanner == "semgrep"
        assert len(scan_result.vulnerabilities) == 1
        
        vuln = scan_result.vulnerabilities[0]
        assert vuln.vuln_type == "python.lang.security.audit.exec-use.exec-use"
        assert vuln.severity == "high"
        assert vuln.line == 10
        assert vuln.source == "semgrep"


def test_diff_guard_no_findings():
    """Test DiffGuard when no findings are returned by Semgrep and diff is small."""
    guard = DiffGuard(llm_tier=None, escalation_threshold=50)
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = '{"results": []}'
        mock_run.return_value = mock_result
        
        scan_result = guard.scan_diff("def safe_func():\n    pass")
        
        assert scan_result.has_findings is False
        assert scan_result.scanner == "none"


def test_diff_guard_escalate_to_llm():
    """Test DiffGuard escalating to LLM when diff is large and Semgrep is clean."""
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    # The LLM scan method isn't implemented deeply in the stub, but we can mock _run_llm_scan directly
    guard = DiffGuard(llm_tier=mock_llm, escalation_threshold=5)
    
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = '{"results": []}'
        mock_run.return_value = mock_result
        
        with patch.object(guard, "_run_llm_scan") as mock_llm_scan:
            mock_llm_scan.return_value = [
                VulnerabilityFinding(vuln_type="IDOR", severity="high", source="llm")
            ]
            
            # Diff > 5 lines
            large_diff = "\n".join([f"line {i}" for i in range(10)])
            scan_result = guard.scan_diff(large_diff)
            
            assert scan_result.has_findings is True
            assert scan_result.scanner == "llm"
            assert scan_result.vulnerabilities[0].vuln_type == "IDOR"
