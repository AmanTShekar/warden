"""Tests for CaMeL interpreter."""

from warden.camel.interpreter import CaMeLInterpreter, LabeledRef
from warden.config import TrustLevel


class TestCaMeLInterpreter:
    def setup_method(self):
        self.interpreter = CaMeLInterpreter()

    def test_quarantine_content_creates_ref(self):
        ref = self.interpreter.quarantine_content("Malicious text", "http://evil.com")
        assert isinstance(ref, LabeledRef)
        assert ref.trust_level == TrustLevel.UNTRUSTED
        assert ref.source == "http://evil.com"
        assert self.interpreter.trusted_refs[ref.ref_id] == ref

    def test_check_tool_call_allows_safe_args(self):
        self.interpreter.quarantine_content("Some text", "test_source")
        assert self.interpreter.check_tool_call("read_file", {"path": "/safe/path.txt"})

    def test_check_tool_call_blocks_control_args(self):
        ref = self.interpreter.quarantine_content("malicious payload", "test_source")
        # Path is a control arg
        assert not self.interpreter.check_tool_call("write_file", {"path": f"/tmp/{ref.ref_id}"})
        # Command is a control arg
        assert not self.interpreter.check_tool_call("run_command", {"cmd": f"echo {ref.ref_id}"})

    def test_check_tool_call_blocks_exact_summary_match(self):
        ref = self.interpreter.quarantine_content("raw untrusted content", "test_source")
        # Argument exactly matches the summary (which might be the raw content due to fallback)
        assert not self.interpreter.check_tool_call("some_tool", {"arg": ref.summary})

    def test_check_tool_call_allows_benign_ref_mention(self):
        ref = self.interpreter.quarantine_content("benign summary", "test_source")
        # Simply mentioning the ref ID in a conceptual argument should be allowed
        assert self.interpreter.check_tool_call("summarize", {"text": f"Here is the data from {ref.ref_id}"})
