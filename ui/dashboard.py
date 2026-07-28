import os
import json
import gradio as gr
from typing import Dict, Any

from warden.config import WardenConfig, Decision
from warden.orchestrator import WardenOrchestrator, GuardResult

def build_dashboard(orchestrator: WardenOrchestrator) -> gr.Blocks:
    """Builds the Gradio UI for Warden."""
    
    def check_live_guard(text: str, source: str):
        result = orchestrator.guard_input(text, source)
        
        decision = result.decision.value.upper()
        if decision == "ALLOW":
            color = "green"
        elif decision == "BLOCK":
            color = "red"
        else:
            color = "orange"
            
        styled_decision = f"<h2 style='color: {color};'>{decision}</h2>"
        explanation = result.explanation
        action = result.action
        
        return styled_decision, explanation, action

    def scan_diff(diff_text: str):
        result = orchestrator.guard_code_commit(diff_text)
        
        # Pull latest stats
        scan_details = []
        if orchestrator.diff_guard:
            # We would normally extract the raw vulns here, but the GuardResult aggregates it.
            scan_details = [[result.action, result.decision.value, result.explanation]]
            
        return scan_details

    def get_routing_stats():
        if orchestrator.router:
            stats = orchestrator.router.get_stats()
            # Convert stats to a format suitable for gr.Dataframe
            rows = [[k, v] for k, v in stats.items()]
            return rows
        return [["Error", "Router not available"]]

    def get_audit_log():
        if orchestrator.audit:
            events = orchestrator.audit.get_recent_events(limit=100)
            rows = []
            for e in events:
                rows.append([
                    e.get("timestamp", ""),
                    e.get("source", ""),
                    e.get("decision", ""),
                    e.get("tier_reached", ""),
                    f"{e.get('latency_ms', 0):.1f}ms",
                    e.get("input_preview", "")[:100]
                ])
            return rows
        return []

    def toggle_shadow_mode(shadow_enabled: bool):
        orchestrator.mode = "shadow" if shadow_enabled else "active"
        return f"Orchestrator mode set to: {orchestrator.mode.upper()}"

    theme = gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="blue",
    )

    with gr.Blocks(title="Warden Security Dashboard", theme=theme) as app:
        gr.Markdown(
            """
            # 🛡️ Warden Security Dashboard
            **Adaptive-Compute Security Guard for AI Coding Agents**
            """
        )
        
        with gr.Tabs():
            # TAB 1: LIVE GUARD
            with gr.Tab("Live Guard"):
                gr.Markdown("Test Warden's Intelligent Routing Engine and Injection Detection in real-time.")
                with gr.Row():
                    with gr.Column(scale=2):
                        live_input = gr.Textbox(lines=5, label="Input Content", placeholder="Enter text, prompt, or tool output...")
                        live_source = gr.Dropdown(choices=["user_direct", "fetched_url", "tool_output", "local_file"], value="fetched_url", label="Content Source")
                        live_btn = gr.Button("Check Content", variant="primary")
                    with gr.Column(scale=1):
                        live_decision = gr.HTML(label="Decision")
                        live_action = gr.Textbox(label="Action Taken")
                        live_explanation = gr.Textbox(label="Explanation", lines=3)
                        
                live_btn.click(
                    fn=check_live_guard,
                    inputs=[live_input, live_source],
                    outputs=[live_decision, live_explanation, live_action]
                )

            # TAB 2: DIFF SCANNER
            with gr.Tab("Diff Scanner"):
                gr.Markdown("Test DiffGuard (Semgrep + Tier 2 LLM verification) on code diffs.")
                with gr.Row():
                    with gr.Column():
                        diff_input = gr.Textbox(lines=10, label="Patch / Diff", placeholder="Paste unified diff here...")
                        diff_btn = gr.Button("Scan Diff", variant="primary")
                    with gr.Column():
                        diff_results = gr.Dataframe(
                            headers=["Action", "Decision", "Explanation"],
                            label="Scan Results"
                        )
                        
                diff_btn.click(
                    fn=scan_diff,
                    inputs=[diff_input],
                    outputs=[diff_results]
                )

            # TAB 3: SECURITY DASHBOARD
            with gr.Tab("Routing Stats"):
                gr.Markdown("Live statistics from the Intelligent Routing Engine.")
                with gr.Row():
                    stats_btn = gr.Button("Refresh Stats")
                with gr.Row():
                    stats_display = gr.Dataframe(
                        headers=["Metric", "Value"],
                        label="Routing Metrics"
                    )
                    
                stats_btn.click(
                    fn=get_routing_stats,
                    inputs=[],
                    outputs=[stats_display]
                )

            # TAB 4: AUDIT LOG
            with gr.Tab("Audit Log"):
                gr.Markdown("Recent security events recorded in the SQLite database.")
                with gr.Row():
                    audit_btn = gr.Button("Refresh Log")
                with gr.Row():
                    audit_display = gr.Dataframe(
                        headers=["Timestamp", "Source", "Decision", "Tier", "Latency", "Preview"],
                        label="Recent Events"
                    )
                    
                audit_btn.click(
                    fn=get_audit_log,
                    inputs=[],
                    outputs=[audit_display]
                )

            # TAB 5: SETTINGS
            with gr.Tab("Settings"):
                gr.Markdown("Configure Warden's operating parameters.")
                with gr.Row():
                    with gr.Column():
                        shadow_toggle = gr.Checkbox(label="Enable Shadow Mode (Log Only, Never Block)", value=False)
                        shadow_status = gr.Textbox(label="Status")
                        shadow_toggle.change(
                            fn=toggle_shadow_mode,
                            inputs=[shadow_toggle],
                            outputs=[shadow_status]
                        )

    return app

if __name__ == "__main__":
    print("Run `warden ui` or `python -m warden.cli ui` instead of running this file directly.")
