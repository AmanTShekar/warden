import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from warden.config import Decision
from warden.routing.router import ThrottleRouter
from warden.camel.interpreter import CaMeLInterpreter
from warden.guards.diff_guard import DiffGuard
from warden.guards.policy import PolicyEngine
from warden.memory.audit_log import AuditLog

logger = logging.getLogger(__name__)

@dataclass
class GuardResult:
    """Result of an orchestrator guard check."""
    is_safe: bool
    decision: Decision
    explanation: str
    action: str = ""  # 'block', 'allow', 'log_only'
    extracted_data: Optional[Dict] = None


class WardenOrchestrator:
    """
    The main entry point for Warden integration.
    
    Acts as a native, dependency-free wrapper around all security modules.
    Intercepts:
    - Inputs (raw user/external data)
    - Tool calls (before execution)
    - Code Commits (diffs before applying)
    
    Modes:
    - ACTIVE: Enforces blocks and policy-based data-flow checks (CaMeL capability tracker)
    - SHADOW: Logs everything, allows everything (for enterprise onboarding)
    - REPORT: (Future) offline analysis mode
    """

    def __init__(
        self,
        router: ThrottleRouter,
        camel: CaMeLInterpreter,
        diff_guard: DiffGuard,
        policy: PolicyEngine,
        audit: AuditLog,
        mode: str = "active"
    ):
        self.router = router
        self.camel = camel
        self.diff_guard = diff_guard
        self.policy = policy
        self.audit = audit
        self.mode = mode.lower()

    def guard_input(self, text: str, source: str) -> GuardResult:
        """
        Intercept raw input coming from an external source or user.
        Routes it through the Intelligent Routing Engine.
        """
        logger.info(f"[Orchestrator] Guarding input from {source}")
        
        # 1. Route the input through the tier cascade
        routing_result = self.router.route(text=text, source=source)
        decision = routing_result.decision
        
        # 2. Apply Shadow Mode override
        if self.mode == "shadow":
            if decision in (Decision.BLOCK, Decision.FLAG):
                logger.warning(f"[Orchestrator][SHADOW MODE] Would have applied {decision.name}, but allowing.")
            return GuardResult(
                is_safe=True,
                decision=decision,
                explanation=routing_result.explanation,
                action="log_only"
            )

        # 3. Handle Active Mode Decisions
        if decision == Decision.BLOCK:
            return GuardResult(
                is_safe=False,
                decision=decision,
                explanation=routing_result.explanation,
                action="block"
            )
            
        # Default fallback for ALLOW/UNCERTAIN in Active Mode
        return GuardResult(
            is_safe=True,
            decision=decision,
            explanation=routing_result.explanation,
            action="allow"
        )

    def guard_tool_call(self, tool_name: str, args: Dict[str, Any], context: str = "") -> GuardResult:
        """
        Intercept a tool call before execution by the LLM.
        Applies the CaMeL capability tracker (data-flow / policy enforcement).
        """
        logger.info(f"[Orchestrator] Guarding tool call: {tool_name}")
        
        # 1. CaMeL Capability Tracker (Data Flow)
        data_flow_safe, violation = self.camel.check_tool_call(tool_name, args)
        if not data_flow_safe:
            msg = f"Data flow violation: {violation}"
            if self.mode == "shadow":
                logger.warning(f"[Orchestrator][SHADOW MODE] {msg}")
            else:
                return GuardResult(is_safe=False, decision=Decision.BLOCK, explanation=msg, action="block")

        # 2. Policy Engine (Declarative Rules)
        policy_result = self.policy.evaluate_tool_call(tool_name, args)
        if policy_result and policy_result.get("decision") == "block":
            msg = f"Policy violation: {policy_result.get('reason', 'Blocked by policy')}"
            if self.mode == "shadow":
                logger.warning(f"[Orchestrator][SHADOW MODE] {msg}")
            else:
                return GuardResult(is_safe=False, decision=Decision.BLOCK, explanation=msg, action="block")
                
        return GuardResult(is_safe=True, decision=Decision.ALLOW, explanation="Tool call authorized", action="allow")

    def guard_code_commit(self, diff: str) -> GuardResult:
        """
        Intercept a code patch before it is applied to the codebase.
        Uses DiffGuard (Semgrep + LLM).
        """
        logger.info("[Orchestrator] Guarding code commit via DiffGuard")
        
        scan_result = self.diff_guard.scan_diff(diff)
        
        if scan_result.has_findings:
            max_severity = scan_result.max_severity
            findings_summary = ", ".join([f"{v.vuln_type} ({v.severity})" for v in scan_result.vulnerabilities])
            msg = f"Vulnerabilities found by {scan_result.scanner}: {findings_summary}"
            
            if self.mode == "shadow":
                logger.warning(f"[Orchestrator][SHADOW MODE] {msg}")
                return GuardResult(is_safe=True, decision=Decision.FLAG, explanation=msg, action="log_only")
                
            # Usually block on critical/high, flag on medium/low
            if max_severity in ("critical", "high"):
                return GuardResult(is_safe=False, decision=Decision.BLOCK, explanation=msg, action="block")
            else:
                return GuardResult(is_safe=True, decision=Decision.FLAG, explanation=msg, action="allow")

        return GuardResult(is_safe=True, decision=Decision.ALLOW, explanation="No vulnerabilities detected", action="allow")
