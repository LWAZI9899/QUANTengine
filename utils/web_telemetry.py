import asyncio
import json
import socket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

# Shared telemetry state updated by engine_main.py (Expanded for DSAC, Edge Decay & Account Telemetry)
latest_telemetry = {
    "timestamp": "00:00:00.000",
    "symbol": "EURUSD",
    "mid": 0.0,
    "spread": 0.0,
    "vol_weight": 1.0,
    "balance": 0.0,
    "equity": 0.0,
    "margin": 0.0,
    "free_margin": 0.0,
    "open_positions": 0,
    "open_pnl": 0.0,
    "closed_pnl": 0.0,
    "closed_trades": 0,
    "win_rate": 0.0,
    "mode": "DORMANT",
    "tfi": 0.0,
    "vpin": 0.0,
    "hawkes_rho": 0.0,
    "fill_prob": 50.0,
    "fills": 0,
    "vb_proxy": 3000.0,
    "va_proxy": 3000.0,
    "dsac_reward": 0.0,
    "cvar_penalty": 0.0,
    "markout_1s": 0.0,
    "markout_5s": 0.0,
    "markout_30s": 0.0,
    "mid_history": [],
    "time_history": [],
}

connected_clients = set()

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantEngine // DSAC & Telemetry Command Center</title>
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
            gap: 12px;
            flex-wrap: wrap;
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
            grid-template-columns: repeat(6, 1fr);
            gap: 8px;
            margin-bottom: 14px;
        }
        @media(max-width: 1024px) {
            .metrics-row { grid-template-columns: repeat(3, 1fr); }
        }
        @media(max-width: 600px) {
            .metrics-row { grid-template-columns: repeat(2, 1fr); }
        }
        .metric-box {
            background: #131722;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }
        .metric-val {
            font-size: 1.08rem;
            font-weight: bold;
            color: #38bdf8;
        }
        .metric-pos {
            color: #34d399;
        }
        .metric-neg {
            color: #f87171;
        }
        .metric-lbl {
            font-size: 0.7rem;
            color: #64748b;
            margin-top: 2px;
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
            <strong style="font-size: 1.2rem;">QUANTENGINE // DSAC & EDGE COMMAND CENTER</strong>
            <div id="clock" style="font-size: 0.8rem; color: #64748b;">Connecting...</div>
        </div>
        <div id="regime-pill" class="pill pill-red">RED MARKET // NO ENTRY</div>
    </div>

    <!-- Account & Trade Performance Row -->
    <div class="metrics-row">
        <div class="metric-box">
            <div class="metric-val" id="m-balance">$0.00</div>
            <div class="metric-lbl">BALANCE</div>
        </div>
        <div class="metric-box">
            <div class="metric-val" id="m-open-pos">0</div>
            <div class="metric-lbl">OPEN TRADES</div>
        </div>
        <div class="metric-box">
            <div class="metric-val" id="m-open-pnl">$0.00</div>
            <div class="metric-lbl">OPEN PNL</div>
        </div>
        <div class="metric-box">
            <div class="metric-val" id="m-closed-pnl">$0.00</div>
            <div class="metric-lbl">CLOSED PNL</div>
        </div>
        <div class="metric-box">
            <div class="metric-val" id="m-margin">$0.00</div>
            <div class="metric-lbl">MARGIN</div>
        </div>
        <div class="metric-box">
            <div class="metric-val" id="m-win-rate">0.0%</div>
            <div class="metric-lbl">WIN RATE</div>
        </div>
    </div>

    <!-- Microstructure & Signal Row -->
    <div class="metrics-row">
        <div class="metric-box"><div class="metric-val" id="m-mid">0.00000</div><div class="metric-lbl">MID PRICE</div></div>
        <div class="metric-box"><div class="metric-val" id="m-dsac">0.00</div><div class="metric-lbl">DSAC REWARD</div></div>
        <div class="metric-box"><div class="metric-val" id="m-prob">50.0%</div><div class="metric-lbl">FILL PROB</div></div>
        <div class="metric-box"><div class="metric-val" id="m-rho">0.00</div><div class="metric-lbl">HAWKES RHO</div></div>
        <div class="metric-box"><div class="metric-val" id="m-markout">0.00</div><div class="metric-lbl">1S MARKOUT</div></div>
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
            <h3>Institutional Risk, Toxicity & Edge Decay</h3>
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

        function formatSignedCurrency(val) {
            const num = Number(val || 0);
            const sign = num > 0 ? '+' : (num < 0 ? '-' : '');
            return `${sign}$${Math.abs(num).toFixed(2)}`;
        }

        function applyPnlColor(el, val) {
            const num = Number(val || 0);
            el.classList.remove('metric-pos', 'metric-neg');
            if (num > 0) el.classList.add('metric-pos');
            else if (num < 0) el.classList.add('metric-neg');
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
            x: ['VPIN', 'TFI', 'Hawkes Rho', '1s Markout', '5s Markout'],
            y: [0, 0, 0, 0, 0],
            type: 'bar',
            marker: { color: ['#f59e0b', '#8b5cf6', '#ec4899', '#34d399', '#38bdf8'] }
        }], { ...layoutBase, yaxis: { range: [-1.5, 1.5] } }, { responsive: true, displayModeBar: false });

        ws.onmessage = (event) => {
            const d = JSON.parse(event.data);
            const balanceVal = Number(d.balance || 0);
            const openPosVal = Number(d.open_positions || 0);
            const openPnlVal = Number(d.open_pnl || 0);
            const closedPnlVal = Number(d.closed_pnl || 0);
            const marginVal = Number(d.margin || 0);
            const winRateVal = Number(d.win_rate || 0);

            document.getElementById('clock').innerText = `${d.symbol} • ${d.timestamp} • Spread: ${Number(d.spread || 0).toFixed(5)}`;
            document.getElementById('m-balance').innerText = `$${balanceVal.toFixed(2)}`;
            document.getElementById('m-open-pos').innerText = `${openPosVal}`;

            const openPnlEl = document.getElementById('m-open-pnl');
            openPnlEl.innerText = formatSignedCurrency(openPnlVal);
            applyPnlColor(openPnlEl, openPnlVal);

            const closedPnlEl = document.getElementById('m-closed-pnl');
            closedPnlEl.innerText = formatSignedCurrency(closedPnlVal);
            applyPnlColor(closedPnlEl, closedPnlVal);

            document.getElementById('m-margin').innerText = `$${marginVal.toFixed(2)}`;
            document.getElementById('m-win-rate').innerText = `${winRateVal.toFixed(1)}%`;

            document.getElementById('m-mid').innerText = Number(d.mid || 0).toFixed(5);
            document.getElementById('m-dsac').innerText = Number(d.dsac_reward || 0).toFixed(2);
            document.getElementById('m-prob').innerText = Number(d.fill_prob || 0).toFixed(1) + '%';
            document.getElementById('m-rho').innerText = Number(d.hawkes_rho || 0).toFixed(2);
            document.getElementById('m-markout').innerText = Number(d.markout_1s || 0).toFixed(2) + 'p';
            document.getElementById('m-fills').innerText = d.fills ?? 0;

            const pill = document.getElementById('regime-pill');
            const isGreen = (d.mode === 'HFT_SCALP' || d.mode === 'STRUCTURAL_REVERSAL') && Number(d.fill_prob || 0) >= 70.0;
            if (isGreen) {
                pill.className = 'pill pill-green';
                pill.innerText = `GREEN MARKET // ${d.mode}`;
            } else {
                pill.className = 'pill pill-red';
                pill.innerText = `RED MARKET // ${d.mode}`;
            }

            Plotly.react('wave3d', [{
                z: buildWaveZ(Number(d.fill_prob || 50), Number(d.hawkes_rho || 0)),
                type: 'surface',
                colorscale: isGreen ? 'Greens' : 'Viridis',
                showscale: false
            }], {
                ...layoutBase,
                margin: { l: 0, r: 0, t: 0, b: 0 }
            });

            const thresholdVol = (Number(d.vb_proxy || 0) + Number(d.va_proxy || 0)) * 0.70;
            Plotly.react('volBar', [{
                x: ['Bid Queue (Vb)', 'Ask Queue (Va)', '70% Entry Gate'],
                y: [Number(d.vb_proxy || 0), Number(d.va_proxy || 0), thresholdVol],
                type: 'bar',
                marker: { color: ['#10b981', '#ef4444', '#38bdf8'] }
            }], layoutBase);

            Plotly.react('priceLine', [{
                x: d.time_history || [],
                y: d.mid_history || [],
                mode: 'lines',
                line: { color: isGreen ? '#10b981' : '#38bdf8', width: 2 }
            }], layoutBase);

            Plotly.react('riskBar', [{
                x: ['VPIN', 'TFI', 'Hawkes Rho', '1s Markout', '5s Markout'],
                y: [
                    Number(d.vpin || 0),
                    Number(d.tfi || 0),
                    Number(d.hawkes_rho || 0),
                    Number(d.markout_1s || 0),
                    Number(d.markout_5s || 0)
                ],
                type: 'bar',
                marker: { color: ['#f59e0b', '#8b5cf6', '#ec4899', '#34d399', '#38bdf8'] }
            }], { ...layoutBase, yaxis: { range: [-1.5, 1.5] } });
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
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        connected_clients.remove(websocket)

def get_local_ip() -> str:
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
    print(f"\n[DSAC Telemetry Dashboard] PC URL    : http://localhost:{port}")
    print(f"[DSAC Telemetry Dashboard] Phone URL : http://{local_ip}:{port} (Ensure phone is on same Wi-Fi)\n")
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
    server = uvicorn.Server(config)
    await server.serve()