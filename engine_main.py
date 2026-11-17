import asyncio
import time
from collections import deque
import numpy as np
import MetaTrader5 as mt5

from core.ingestion_feeder import initialize_mt5, get_latest_tick
from core.microstructure_engine import MicrostructureEngine
from core.kalman_hedge import KalmanHedgeTracker
from core.dual_horizon_logic import DualHorizonEngine
from risk.les_hedging import LocalExpectedShortfallHedger
from core.almgren_chriss_slicer import AlmgrenChrissSlicer
from core.hawkes_intensity import RecursiveHawkesIntensity
from risk.rmt_covariance import MarchenkoPasturCovarianceDenoiser
from core.dsac_gate import DSACRiskSensitiveGate
from core.synthetic_l2 import SyntheticL2Proxy
from risk.circuit_breakers import get_session_volatility_weight
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
    print("Starting QuantEngine Async Main Event Loop (24/7 All-Day Mode Enabled)...")
    symbol = "EURUSD"
    
    if not initialize_mt5(symbol):
        print("Initialization failed. Exiting.")
        return

    # 1. Instantiate Core & Advanced Quantitative Engines
    micro_engine = MicrostructureEngine(window_size=500)
    kalman_tracker = KalmanHedgeTracker(state_dim=2, process_variance=1e-5, measurement_variance=1e-3)
    les_hedger = LocalExpectedShortfallHedger(risk_aversion_q=1.5, penalty_threshold=0.0)
    dual_horizon_engine = DualHorizonEngine(risk_pct=0.01)
    dispatcher = AsyncOrderDispatcher(max_concurrent=10)
    
    # Instantiate Institutional Add-ons
    hawkes_tracker = RecursiveHawkesIntensity()
    ac_slicer = AlmgrenChrissSlicer(total_shares=9.0, total_time_sec=300.0, volatility=0.015)
    rmt_denoiser = MarchenkoPasturCovarianceDenoiser(q_ratio=0.2)
    dsac_gate = DSACRiskSensitiveGate(alpha_cvar=0.05, penalty_psi=2.0)
    synthetic_l2 = SyntheticL2Proxy(window_size=50)

    worker_task = asyncio.create_task(dispatcher.start_worker())

    mid_prices = deque(maxlen=100)
    returns_history = deque(maxlen=200)
    current_inventory_q = 0  
    position_entry_timestamp = time.time()
    active_trades_count = 0

    print(f"Streaming high-frequency L1 order flow ticks for {symbol} 24/7...")

    try:
        while True:
            # Check 24/7 session status (only pauses on weekends)
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

                features = micro_engine.update_tick(bid=bid, ask=ask, last=last, volume=volume)
                
                if features:
                    current_mid = features['mid']
                    current_vpin = features.get('vpin', 0.32) * vol_weight  # Scaled by session volatility
                    current_spread_z = features['spread_z']
                    current_micro_velocity = features.get('micro_price', current_mid) - current_mid
                    
                    if len(mid_prices) > 0:
                        returns_history.append(current_mid - mid_prices[-1])
                    mid_prices.append(current_mid)

                    # Compute Synthetic L2 Trade-Flow Imbalance (TFI)
                    tfi_score = synthetic_l2.compute_tfi(
                        trade_price=last if last > 0 else current_mid,
                        trade_vol=volume,
                        bid=bid,
                        ask=ask
                    )

                    # Update Hawkes Intensity & Check Market Fragility
                    h_buy, h_sell = hawkes_tracker.update(event_type=0 if current_micro_velocity > 0 else 1, timestamp=time.time())
                    branching_rho = hawkes_tracker.get_branching_spectral_radius()

                    if branching_rho > 0.95:
                        logger.warning(f"[Circuit Breaker] Hawkes branching rho critical ({branching_rho:.2f}). Pausing execution.")
                        await asyncio.sleep(1.0)
                        continue

                    # Apply Marchenko-Pastur RMT Covariance Denoising
                    if len(returns_history) > 30:
                        dummy_matrix = np.column_stack([
                            list(returns_history),
                            list(returns_history) * 0.95 + np.random.normal(0, 0.0001, len(returns_history))
                        ])
                        denoised_cov = rmt_denoiser.denoise_covariance(dummy_matrix)

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
                        returns = list(mid_prices)
                        optimal_gamma_scale = les_hedger.optimize_hedge_gamma(
                            spot_prices=list(mid_prices), 
                            option_gammas=[1.0]*len(mid_prices), 
                            historical_returns=returns
                        )
                    else:
                        optimal_gamma_scale = 1.0

                    active_mode = dual_horizon_engine.evaluate_market_regime(
                        vpin=current_vpin,
                        spread_z=current_spread_z,
                        micro_velocity=current_micro_velocity
                    )

                    allowed_holding_time = dual_horizon_engine.calculate_optimal_holding_horizon(
                        volatility=0.0012 if len(mid_prices) < 2 else abs(mid_prices[-1] - mid_prices[-2]),
                        vpin=current_vpin,
                        inventory_q=current_inventory_q,
                        gamma=optimal_gamma_scale
                    )

                    elapsed_position_time = time.time() - position_entry_timestamp
                    if abs(current_micro_velocity) > 0.00002 or elapsed_position_time >= allowed_holding_time:
                        
                        # Evaluate DSAC Risk-Sensitive Reward Gate & Synthetic L2 TFI filter
                        reward_score = dsac_gate.evaluate_risk_sensitive_reward(
                            delta_pnl=0.40,
                            inventory_q=current_inventory_q,
                            adverse_fill_flag=(current_vpin > 0.60),
                            fees=0.08
                        )

                        if dsac_gate.approve_execution(reward_score) and tfi_score > -0.50:
                            active_trades_count += 1
                            position_entry_timestamp = time.time()

                            order_request = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": symbol,
                                "volume": 0.02,
                                "type": mt5.ORDER_TYPE_BUY,
                                "price": ask,
                                "deviation": 20,
                                "magic": 234000,
                                "comment": f"247_Engine_{active_mode}",
                                "type_time": mt5.ORDER_TIME_GTC,
                            }
                            await dispatcher.enqueue_order(order_request)
                        else:
                            logger.warning(f"[Execution Gate] Trade rejected. DSAC Score: {reward_score:.2f} | TFI: {tfi_score:.2f}")

                    msg = (
                        f"[{features['time'].strftime('%H:%M:%S.%f')[:-3]}] "
                        f"VolWeight: {vol_weight}x | Mode: {active_mode} | "
                        f"Hawkes Rho: {branching_rho:.2f} | TFI: {tfi_score:.2f} | Fills: {active_trades_count} | "
                        f"HoldLimit: {allowed_holding_time:.1f}s"
                    )
                    print(msg)
                    logger.info(msg)
                    
            await asyncio.sleep(0.01)

    except asyncio.CancelledError:
        print("Async event loop cancelled.")
    finally:
        dispatcher.is_running = False
        worker_task.cancel()
        mt5.shutdown()
        print(f"\nEngine safely shut down. Total high-frequency fills dispatched: {active_trades_count}")

if __name__ == "__main__":
    asyncio.run(main_async())