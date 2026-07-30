from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import logging

from warden.config import WardenConfig
from warden.cli import create_router
from warden.camel.interpreter import CaMeLInterpreter
from warden.guards.diff_guard import DiffGuard
from warden.guards.policy import PolicyEngine
from warden.memory.audit_log import AuditLog
from warden.orchestrator import WardenOrchestrator

logger = logging.getLogger(__name__)

app = FastAPI(title="Warden Web UI")

# Global Initialization
config = WardenConfig.from_env()
router = create_router(config)
audit = AuditLog("warden_audit.db")
audit.initialize()
policy = PolicyEngine()
diff_guard = DiffGuard()

# We pass the router's tier2 model directly to camel if available
camel = CaMeLInterpreter(llm=router.tier2, policy=policy)

orchestrator = WardenOrchestrator(
    router=router,
    camel=camel,
    diff_guard=diff_guard,
    policy=policy,
    audit=audit
)

class GuardRequest(BaseModel):
    text: str
    source: str = "user_direct"

@app.post("/api/guard")
async def guard_endpoint(req: GuardRequest):
    import time
    start = time.perf_counter()
    
    if req.source == "code_diff":
        result = orchestrator.guard_code_commit(req.text)
    else:
        result = orchestrator.guard_input(req.text, req.source)
        
    latency_ms = (time.perf_counter() - start) * 1000
    
    return {
        "decision": result.decision.value.upper(),
        "explanation": result.explanation,
        "action": result.action,
        "latency_ms": round(latency_ms, 2)
    }

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Warden</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0a0a0a;
            --surface: #121212;
            --border: #262626;
            --border-hover: #404040;
            --text-main: #ededed;
            --text-dim: #888888;
            
            --ok: #2ecca6;
            --err: #ef4444;
            --warn: #eab308;
            
            --font: 'Inter', -apple-system, sans-serif;
        }
        
        * { box-sizing: border-box; }

        body {
            background-color: var(--bg);
            color: var(--text-main);
            font-family: var(--font);
            margin: 0;
            padding: 8vh 20px;
            display: flex;
            justify-content: center;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }

        .container {
            width: 100%;
            max-width: 900px;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        .header {
            text-align: center;
            margin-bottom: 24px;
        }

        h1 {
            font-size: 28px;
            font-weight: 600;
            margin: 0 0 8px 0;
            letter-spacing: -0.5px;
        }
        
        .subtitle {
            color: var(--text-dim);
            font-size: 15px;
        }

        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.2);
        }

        .label {
            font-size: 13px;
            font-weight: 500;
            color: var(--text-dim);
            margin-bottom: 12px;
            display: block;
        }

        textarea, select {
            width: 100%;
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text-main);
            font-family: var(--font);
            font-size: 14px;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 24px;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        textarea { resize: vertical; min-height: 140px; line-height: 1.6; }
        
        textarea:focus, select:focus { 
            border-color: #666; 
            box-shadow: 0 0 0 1px #666;
        }

        button {
            width: 100%;
            background: #ffffff;
            color: #000000;
            font-family: var(--font);
            font-weight: 500;
            font-size: 14px;
            padding: 14px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            transition: transform 0.1s, opacity 0.2s;
        }

        button:hover { opacity: 0.9; }
        button:active { transform: scale(0.98); }
        button:disabled { background: #333; color: #666; cursor: not-allowed; }

        .result-area {
            margin-top: 32px;
            padding-top: 32px;
            border-top: 1px solid var(--border);
        }

        .decision-badge {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-bottom: 20px;
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-dim);
            border: 1px solid var(--border);
        }

        .decision-badge.allow { background: rgba(46, 204, 166, 0.1); color: var(--ok); border: 1px solid rgba(46, 204, 166, 0.2); }
        .decision-badge.block { background: rgba(239, 68, 68, 0.1); color: var(--err); border: 1px solid rgba(239, 68, 68, 0.2); }
        .decision-badge.flag { background: rgba(234, 179, 8, 0.1); color: var(--warn); border: 1px solid rgba(234, 179, 8, 0.2); }

        .details-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 16px;
        }
        
        .detail-item {
            background: var(--bg);
            border: 1px solid var(--border);
            padding: 16px;
            border-radius: 8px;
        }

        .detail-title {
            font-size: 12px;
            color: var(--text-dim);
            margin-bottom: 6px;
        }

        .detail-value {
            font-size: 14px;
            color: var(--text-main);
        }

        .loader {
            display: none;
            text-align: center;
            margin-top: 24px;
            color: var(--text-dim);
            font-size: 14px;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; }
        }
    </style>
</head>
<body>

    <div class="container">
        <div class="header">
            <h1>Warden</h1>
            <div class="subtitle">Adaptive-Compute Security Guard</div>
        </div>

        <div class="card">
            <span class="label">Incoming Payload</span>
            <textarea id="payload" placeholder="Paste prompt injection or payload..."></textarea>
            
            <span class="label">Context Source</span>
            <select id="source">
                <option value="user_direct">User Direct</option>
                <option value="fetched_url" selected>Fetched URL</option>
                <option value="tool_output">Tool Output</option>
                <option value="code_diff">Code Diff (CI/CD)</option>
            </select>
            
            <button id="scanBtn" onclick="runScan()">Scan Request</button>
            <div id="loader" class="loader">Processing through routing engine...</div>

            <div id="resultArea" class="result-area">
                <span class="label">Routing Decision</span>
                <div id="decisionBadge" class="decision-badge">PENDING</div>

                <div class="details-grid">
                    <div class="detail-item">
                        <div class="detail-title">Action Taken</div>
                        <div id="actionValue" class="detail-value">Awaiting scan...</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-title">Explanation</div>
                        <div id="explanationValue" class="detail-value">Awaiting scan...</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-title">Total Latency</div>
                        <div id="latencyValue" class="detail-value">-</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function runScan() {
            const text = document.getElementById('payload').value;
            const source = document.getElementById('source').value;
            const btn = document.getElementById('scanBtn');
            const loader = document.getElementById('loader');
            const badge = document.getElementById('decisionBadge');
            
            if (!text.trim()) return;

            btn.disabled = true;
            loader.style.display = 'block';
            
            badge.className = 'decision-badge';
            badge.innerText = 'ANALYZING...';
            document.getElementById('actionValue').innerText = 'Routing...';
            document.getElementById('explanationValue').innerText = 'Analyzing input against security tiers...';
            document.getElementById('latencyValue').innerText = '...';

            try {
                const response = await fetch('/api/guard', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, source })
                });
                
                const result = await response.json();
                
                badge.className = 'decision-badge ' + result.decision.toLowerCase();
                badge.innerText = result.decision;
                
                document.getElementById('actionValue').innerText = result.action;
                document.getElementById('explanationValue').innerText = result.explanation;
                document.getElementById('latencyValue').innerText = result.latency_ms + ' ms';
                
            } catch (err) {
                alert("Connection error. Ensure the backend is running.");
            } finally {
                loader.style.display = 'none';
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return HTML_CONTENT

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

