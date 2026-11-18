import asyncio
import time
from collections import deque
import numpy as np
import MetaTrader5 as mt5

from core.ingestion_feeder import initialize_mt5, get_latest_tick
from core.microstructure_engine import MicrostructureEngine
from core.kalman_hedge import KalmanHedgeTracker
from core.dual_horizon_logic import DualHorizonRegimeEngine as DualHorizonEngine
from risk.les_hedging import LocalExpectedShortfallHedger
from core.almgren_chriss_slicer import AlmgrenChrissSlicer
from core.hawkes_intensity import RecursiveHawkesIntensity
from risk.rmt_covariance import MarchenkoPasturCovarianceDenoiser
from core.dsac_gate import DSACRiskSensitiveGate
from core.synthetic_l2 import SyntheticL2Proxy
from risk.circuit_breakers import get_session_volatility_weight
from utils.web_telemetry import start_telemetry_server, latest_telemetry

# Analytical queue probability gate (silent background run)
from sims.sim_monte_carlo_queue import simulate_queue_depletion
from utils.logger import logger


class AsyncOrderDispatcher:
    """Non-blocking asynchronous order dispatcher supporting up to 10 orders/sec."""
    def __init__(self, max_concurrent=10):
        self.queue = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.is_running = False

    async def start_worker(self):
        self.is_running = True
        while self.is_running:
            request = await self.queue.get()
            try:
                await self.execute_order(request)
            except Exception as e:
                logger.error(f"Async order execution failed: {e}")
            finally:
                self.queue.task_done()

    async def execute_order(self, request):
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, mt5.order_send, request)
        if result and result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.warning(f"Order failed with retcode: {result.retcode}")
        elif result:
            logger.info(f"Successfully filled order batch: {result.order}")

    async def enqueue_order(self, request):
        if self.queue.qsize() < self.max_concurrent * 5:
            await self.queue.put(request)
        else:
            logger.warning("Order queue saturated; dropping stale slice to prevent slippage.")


async def main_async():
    print("Starting Hardened QuantEngine Async Main Event Loop...")
    symbol = "EURUSD"
    
    if not initialize_mt5(symbol):
        print("Initialization failed. Exiting.")
        return

    # 1. Instantiate Core & Advanced Quantitative Engines
    micro_engine = MicrostructureEngine(window_size=500)
    kalman_tracker = KalmanHedgeTracker(state_dim=2, process_variance=1e-5, measurement_variance=1e-3)
    les_hedger = LocalExpectedShortfallHedger(risk_aversion_q=1.5, penalty_threshold=0.0)
    
    dual_horizon_engine = DualHorizonEngine(base_gamma=0.1, vpin_threshold=0.55, ctox=3.0)
    dispatcher = AsyncOrderDispatcher(max_concurrent=10)
    
    hawkes_tracker = RecursiveHawkesIntensity()
    ac_slicer = AlmgrenChrissSlicer(total_shares=9.0, total_time_sec=300.0, volatility=0.015)
    rmt_denoiser = MarchenkoPasturCovarianceDenoiser(q_ratio=0.2)
    dsac_gate = DSACRiskSensitiveGate(alpha_cvar=0.05, penalty_psi=2.0)
    synthetic_l2 = SyntheticL2Proxy(window_size=50)

    worker_task = asyncio.create_task(dispatcher.start_worker())
    telemetry_task = asyncio.create_task(start_telemetry_server(port=8000))

    mid_prices = deque(maxlen=100)
    returns_history = deque(maxlen=200)
    timestamps = deque(maxlen=100)
    
    current_inventory_q = 0  
    position_entry_timestamp = time.time()
    active_trades_count = 0
    
    # Throttle control for console printing (e.g., print every 0.5 seconds)
    last_print_time = 0.0
    print_interval = 0.5 

    print(f"Streaming high-frequency L1 order flow ticks for {symbol} with validated data pipelines...")

    try:
        while True:
            is_active, vol_weight = get_session_volatility_weight()
            if not is_active:
                logger.info("[Weekend Guardrail] Forex markets closed. Engine resting until Monday open.")
                await asyncio.sleep(60.0)
                continue

            tick = get_latest_tick(symbol)
            if tick:
                bid = tick['bid']
                ask = tick['ask']
                last = tick.get('last', 0.0)
                volume = tick.get('volume', 1.0)
                current_time = time.time()

                features = micro_engine.update_tick(bid=bid, ask=ask, last=last, volume=volume)
                
                if features:
                    current_mid = features['mid']
                    current_spread = ask - bid
                    
                    current_vpin = features.get('vpin', 0.35) * vol_weight
                    current_spread_z = features['spread_z']
                    
                    micro_price = features.get('micro_price', current_mid)
                    if len(mid_prices) > 0 and len(timestamps) > 0:
                        dt = max(1e-3, current_time - timestamps[-1])
                        current_micro_velocity = (micro_price - mid_prices[-1]) / dt
                    else:
                        current_micro_velocity = 0.0
                    
                    if len(mid_prices) > 0:
                        returns_history.append(current_mid - mid_prices[-1])
                    mid_prices.append(current_mid)
                    timestamps.append(current_time)

                    # Compute L1-Derived Trade-Flow Imbalance (TFI) Proxy
                    tfi_score = synthetic_l2.compute_tfi(
                        trade_price=last if last > 0 else current_mid,
                        trade_vol=volume,
                        bid=bid,
                        ask=ask
                    )

                    # Update Hawkes Intensity & Check Market Fragility
                    h_buy, h_sell = hawkes_tracker.update(event_type=0 if current_micro_velocity > 0 else 1, timestamp=current_time)
                    branching_rho = hawkes_tracker.get_branching_spectral_radius()

                    if branching_rho > 0.95:
                        logger.warning(f"[Circuit Breaker] Hawkes branching rho critical ({branching_rho:.2f}). Pausing execution.")
                        await asyncio.sleep(1.0)
                        continue

                    # RMT Covariance Denoising
                    if len(returns_history) > 30:
                        returns_arr = np.array(list(returns_history), dtype=float)
                        return_matrix = np.column_stack([returns_arr, np.roll(returns_arr, 1)])
                        denoised_cov = rmt_denoiser.denoise_covariance(return_matrix)
                    else:
                        denoised_cov = None

                    # Kalman Filter Hedge Ratio
                    if len(mid_prices) > 5:
                        y_t = current_mid
                        x_t = [1.0, mid_prices[-2]]  
                        kalman_res = kalman_tracker.update(y_t, x_t)
                        dynamic_beta = kalman_res['hedge_ratio']
                    else:
                        dynamic_beta = 1.0

                    # LES Gamma Scaling
                    if len(mid_prices) > 10:
                        spot_arr = np.array(list(mid_prices), dtype=float)
                        gammas_arr = np.ones_like(spot_arr)
                        returns_arr = np.array(list(returns_history), dtype=float) if len(returns_history) > 0 else np.array([0.0])
                        
                        optimal_gamma_scale = les_hedger.optimize_hedge_gamma(
                            spot_prices=spot_arr, 
                            option_gammas=gammas_arr, 
                            historical_returns=returns_arr
                        )
                    else:
                        optimal_gamma_scale = 1.0

                    # Dynamic L1 tick volumes from MT5 for queue simulation
                    bid_vol_raw = tick.get('bid_volume', 0.0)
                    ask_vol_raw = tick.get('ask_volume', 0.0)
                    vb_proxy = bid_vol_raw if bid_vol_raw > 0 else volume * 1500.0
                    va_proxy = ask_vol_raw if ask_vol_raw > 0 else volume * 1200.0
                    
                    fill_probability = simulate_queue_depletion(vb=vb_proxy, va=va_proxy, rho_ab=0.15, num_paths=1000)

                    # Evaluate entry gateway using DualHorizonRegimeEngine methods
                    active_mode = dual_horizon_engine.evaluate_entry_gate(
                        spread_z=current_spread_z,
                        vpin=current_vpin,
                        upward_prob=fill_probability,
                        branching_rho=branching_rho
                    )

                    elapsed_position_time = current_time - position_entry_timestamp
                    if active_mode in ["HFT_SCALP", "STRUCTURAL_REVERSAL"]:
                        
                        reward_score = dsac_gate.evaluate_risk_sensitive_reward(
                            delta_pnl=0.40,
                            inventory_q=current_inventory_q,
                            adverse_fill_flag=(current_vpin > 0.60),
                            fees=0.08
                        )

                        if dsac_gate.approve_execution(reward_score) and tfi_score > -0.50 and fill_probability >= 0.45:
                            active_trades_count += 1
                            position_entry_timestamp = current_time

                            order_request = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": symbol,
                                "volume": 0.02,
                                "type": mt5.ORDER_TYPE_BUY,
                                "price": ask,
                                "deviation": 20,
                                "magic": 234000,
                                "comment": f"Hardened_{active_mode}",
                                "type_time": mt5.ORDER_TIME_GTC,
                            }
                            await dispatcher.enqueue_order(order_request)
                        else:
                            logger.warning(
                                f"[Execution Gate] Trade rejected. DSAC Score: {reward_score:.2f} | "
                                f"TFI: {tfi_score:.2f} | Fill P(Prob): {fill_probability*100:.1f}%"
                            )

                    # Throttle console prints to once every 0.5 seconds while background loop runs at full speed
                    if current_time - last_print_time >= print_interval:
                        msg = (
                            f"[{features['time'].strftime('%H:%M:%S.%f')[:-3]}] "
                            f"Mid: {current_mid:.5f} | Spread: {current_spread:.5f} | "
                            f"VolWeight: {vol_weight}x | Mode: {active_mode} | "
                            f"TFI: {tfi_score:+.2f} | VPIN: {current_vpin:.2f} | "
                            f"Hawkes Rho: {branching_rho:.2f} | Fill Prob: {fill_probability*100:.1f}% | "
                            f"Fills: {active_trades_count}"
                        )
                        print(msg)
                        logger.info(msg)
                        last_print_time = current_time

                    # Feed live states to the real-time web telemetry dashboard
                    latest_telemetry.update({
                        "timestamp": features['time'].strftime('%H:%M:%S.%f')[:-3],
                        "symbol": symbol,
                        "mid": float(current_mid),
                        "spread": float(current_spread),
                        "vol_weight": float(vol_weight),
                        "mode": active_mode,
                        "tfi": float(tfi_score),
                        "vpin": float(current_vpin),
                        "hawkes_rho": float(branching_rho),
                        "fill_prob": float(fill_probability * 100.0),
                        "fills": active_trades_count,
                        "vb_proxy": float(vb_proxy),
                        "va_proxy": float(va_proxy),
                        "mid_history": list(mid_prices)[-40:],
                        "time_history": [f"T-{i}" for i in range(len(list(mid_prices)[-40:]), 0, -1)]
                    })
                    
            await asyncio.sleep(0.01)

    except asyncio.CancelledError:
        print("Async event loop cancelled.")
    finally:
        dispatcher.is_running = False
        worker_task.cancel()
        mt5.shutdown()
        print(f"\nEngine safely shut down. Total executed fills: {active_trades_count}")

if __name__ == "__main__":
    asyncio.run(main_async())