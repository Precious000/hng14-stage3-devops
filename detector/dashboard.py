import asyncio
import time
import psutil
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()
_state = {}


def set_state(state: dict):
    _state.update(state)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    s = _state
    banned = s.get("banned_ips", [])
    top_ips = s.get("top_ips", [])
    global_rps = s.get("global_rps", 0)
    mean, stddev = s.get("mean", 0), s.get("stddev", 0)
    uptime = s.get("uptime", 0)
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent

    banned_rows = "".join(f"<tr><td>{ip}</td></tr>" for ip in banned) or "<tr><td>None</td></tr>"
    top_rows = "".join(f"<tr><td>{ip}</td><td>{count}</td></tr>" for ip, count in top_ips)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>HNG Anomaly Detector</title>
      <meta http-equiv="refresh" content="3">
      <style>
        body {{ font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
        h1 {{ color: #58a6ff; }}
        h2 {{ color: #f0883e; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #30363d; padding: 8px 12px; text-align: left; }}
        th {{ background: #161b22; color: #58a6ff; }}
        .metric {{ display: inline-block; background: #161b22; padding: 12px 20px;
                   margin: 8px; border-radius: 6px; border: 1px solid #30363d; }}
        .metric span {{ display: block; font-size: 24px; color: #3fb950; }}
      </style>
    </head>
    <body>
      <h1>HNG Anomaly Detection Dashboard</h1>
      <div>
        <div class="metric">Global req/s<span>{global_rps:.2f}</span></div>
        <div class="metric">CPU %<span>{cpu:.1f}</span></div>
        <div class="metric">Memory %<span>{mem:.1f}</span></div>
        <div class="metric">Baseline mean<span>{mean:.4f}</span></div>
        <div class="metric">Baseline stddev<span>{stddev:.4f}</span></div>
        <div class="metric">Uptime (s)<span>{int(uptime)}</span></div>
      </div>

      <h2>Banned IPs</h2>
      <table><tr><th>IP</th></tr>{banned_rows}</table>

      <h2>Top 10 Source IPs (last 60s)</h2>
      <table>
        <tr><th>IP</th><th>Requests</th></tr>
        {top_rows}
      </table>
    </body>
    </html>
    """
    return html


@app.get("/metrics")
async def metrics():
    s = _state
    mean, stddev = s.get("mean", 0), s.get("stddev", 0)
    return {
        "global_rps": s.get("global_rps", 0),
        "banned_ips": s.get("banned_ips", []),
        "top_ips": s.get("top_ips", []),
        "mean": mean,
        "stddev": stddev,
        "uptime": s.get("uptime", 0),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
    }


async def run_dashboard(port: int):
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
