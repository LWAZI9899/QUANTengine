import asyncio
import json
import socket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

# Shared telemetry state updated by engine_main.py
latest_telemetry = {
    "timestamp": "00:00:00.000",
    "symbol": "EURUSD",
    "mid": 0.0,
    "spread": 0.0,
    "vol_weight": 1.0,
    "mode": "DORMANT",
    "tfi": 0.0,
    "vpin": 0.0,
    "hawkes_rho": 0.0,
    "fill_prob": 50.0,
    "fills": 0,
    "vb_proxy": 3000.0,
    "va_proxy": 3000.0,
    "mid_history": [],
    "time_history": []
}

connected_clients = set()

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantEngine Live Telemetry</title>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        body {
            background-color: #0b0e14;
            color: #e2e8f0;
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 16px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #1e293b;
            padding-bottom: 12px;
            margin-bottom: 16px;
        }
        .pill {
            padding: 8px 18px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 0.9rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            transition: all 0.25s ease;
        }
        .pill-green {
            background-color: rgba(16, 185, 129, 0.2);
            color: #34d399;
            border: 1px solid #10b981;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.4);
        }
        .pill-red {
            background-color: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border: 1px solid #ef4444;
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.25);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 16px;
        }
        .card {
            background-color: #131722;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 14px;
        }
        .card h3 {
            margin: 0 0 10px 0;
            font-size: 0.85rem;
            color: #94a3b8;
            text-transform: uppercase;
        }
        .metrics-row {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 16px;
        }
        .metric-box {
            background: #131722;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }
        .metric-val {
            font-size: 1.1rem;
            font-weight: bold;
            color: #38bdf8;
        }
        .metric-lbl {
            font-size: 0.7rem;
            color: #64748b;
        }
        .chart-box {
            width: 100%;
            height: 280px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <strong style="font-size: 1.2rem;">QUANTENGINE // LIVE L1</strong>
            <div id="clock" style="font-size: 0.8rem; color: #64748b;">Connecting...</div>
        </div>
        <div id="regime-pill" class="pill pill-red">RED MARKET // NO ENTRY</div>
    </div>

    <div class="metrics-row">
        <div class="metric-box"><div class="metric-val" id="m-mid">0.00000</div><div class="metric-lbl">MID PRICE</div></div>
        <div class="metric-box"><div class="metric-val" id="m-prob">50.0%</div><div class="metric-lbl">FILL PROB</div></div>
        <div class="metric-box"><div class="metric-val" id="m-rho">0.00</div><div class="metric-lbl">HAWKES RHO</div></div>
        <div class="metric-box"><div class="metric-val" id="m-fills">0</div><div class="metric-lbl">TOTAL FILLS</div></div>
    </div>

    <div class="grid">
        <div class="card">
            <h3>3D Monte Carlo / Queue Depletion Wave</h3>
            <div id="wave3d" class="chart-box"></div>
        </div>
        <div class="card">
            <h3>Entry Potential & Queue Volume Imbalance</h3>
            <div id="volBar" class="chart-box"></div>
        </div>
        <div class="card">
            <h3>Live Micro-Mid Price Trajectory</h3>
            <div id="priceLine" class="chart-box"></div>
        </div>
        <div class="card">
            <h3>Institutional Risk Gauges (VPIN & TFI)</h3>
            <div id="riskBar" class="chart-box"></div>
        </div>
    </div>

    <script>
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

        const layoutBase = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#94a3b8', size: 10 },
            margin: { l: 35, r: 15, t: 10, b: 30 }
        };

        // Initialize 3D Wave Surface
        function buildWaveZ(fillProb, rho) {
            let z = [];
            let amp = (fillProb / 50.0);
            let freq = 0.4 + rho * 0.5;
            for (let x = 0; x < 15; x++) {
                let row = [];
                for (let y = 0; y < 15; y++) {
                    row.push(Math.sin(x * freq) * Math.cos(y * freq) * amp + (fillProb / 100.0));
                }
                z.push(row);
            }
            return z;
        }

        Plotly.newPlot('wave3d', [{
            z: buildWaveZ(50, 0.75),
            type: 'surface',
            colorscale: 'Viridis',
            showscale: false
        }], {
            ...layoutBase,
            margin: { l: 0, r: 0, t: 0, b: 0 },
            scene: {
                xaxis: { showgrid: false, zeroline: false, title: '' },
                yaxis: { showgrid: false, zeroline: false, title: '' },
                zaxis: { showgrid: true, gridcolor: '#1e293b', title: '' }
            }
        }, { responsive: true, displayModeBar: false });

        Plotly.newPlot('volBar', [{
            x: ['Bid Queue (Vb)', 'Ask Queue (Va)', 'Entry Threshold'],
            y: [3000, 3000, 4200],
            type: 'bar',
            marker: { color: ['#10b981', '#ef4444', '#38bdf8'] }
        }], layoutBase, { responsive: true, displayModeBar: false });

        Plotly.newPlot('priceLine', [{
            x: [],
            y: [],
            mode: 'lines',
            line: { color: '#38bdf8', width: 2 }
        }], layoutBase, { responsive: true, displayModeBar: false });

        Plotly.newPlot('riskBar', [{
            x: ['VPIN Toxicity', 'TFI Imbalance', 'Hawkes Fragility'],
            y: [0, 0, 0],
            type: 'bar',
            marker: { color: ['#f59e0b', '#8b5cf6', '#ec4899'] }
        }], { ...layoutBase, yaxis: { range: [-1, 1.2] } }, { responsive: true, displayModeBar: false });

        ws.onmessage = (event) => {
            const d = JSON.parse(event.data);
            document.getElementById('clock').innerText = `${d.symbol} • ${d.timestamp} • Spread: ${d.spread.toFixed(5)}`;
            document.getElementById('m-mid').innerText = d.mid.toFixed(5);
            document.getElementById('m-prob').innerText = d.fill_prob.toFixed(1) + '%';
            document.getElementById('m-rho').innerText = d.hawkes_rho.toFixed(2);
            document.getElementById('m-fills').innerText = d.fills;

            // Green/Red Market Pill Toggle
            const pill = document.getElementById('regime-pill');
            const isGreen = (d.mode === 'HFT_SCALP' || d.mode === 'STRUCTURAL_REVERSAL') && d.fill_prob >= 70.0;
            if (isGreen) {
                pill.className = 'pill pill-green';
                pill.innerText = `GREEN MARKET // ${d.mode}`;
            } else {
                pill.className = 'pill pill-red';
                pill.innerText = `RED MARKET // ${d.mode}`;
            }

            // Update 3D Wave
            Plotly.react('wave3d', [{
                z: buildWaveZ(d.fill_prob, d.hawkes_rho),
                type: 'surface',
                colorscale: isGreen ? 'Greens' : 'Viridis',
                showscale: false
            }], {
                ...layoutBase,
                margin: { l: 0, r: 0, t: 0, b: 0 }
            });

            // Update Entry Volume Bar Chart
            const thresholdVol = (d.vb_proxy + d.va_proxy) * 0.70;
            Plotly.react('volBar', [{
                x: ['Bid Queue (Vb)', 'Ask Queue (Va)', '70% Entry Gate'],
                y: [d.vb_proxy, d.va_proxy, thresholdVol],
                type: 'bar',
                marker: { color: ['#10b981', '#ef4444', '#38bdf8'] }
            }], layoutBase);

            // Update Line Chart
            Plotly.react('priceLine', [{
                x: d.time_history,
                y: d.mid_history,
                mode: 'lines',
                line: { color: isGreen ? '#10b981' : '#38bdf8', width: 2 }
            }], layoutBase);

            // Update Risk Pill Bars
            Plotly.react('riskBar', [{
                x: ['VPIN Toxicity', 'TFI Imbalance', 'Hawkes Rho'],
                y: [d.vpin, d.tfi, d.hawkes_rho],
                type: 'bar',
                marker: { color: ['#f59e0b', '#8b5cf6', '#ec4899'] }
            }], { ...layoutBase, yaxis: { range: [-1, 1.2] } });
        };
    </script>
</body>
</html>
"""

@app.get("/")
async def get_dashboard():
    return HTMLResponse(HTML_DASHBOARD)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        while True:
            await websocket.send_text(json.dumps(latest_telemetry))
            await asyncio.sleep(0.25)  # 4 FPS smooth mobile & desktop refresh
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

def get_local_ip() -> str:
    """Finds your PC's local Wi-Fi IP address so your phone can connect."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

async def start_telemetry_server(port: int = 8000):
    local_ip = get_local_ip()
    print(f"\n[Telemetry Dashboard] PC URL    : http://localhost:{port}")
    print(f"[Telemetry Dashboard] Phone URL : http://{local_ip}:{port} (Ensure phone is on same Wi-Fi)\n")
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
    server = uvicorn.Server(config)
    await server.serve()