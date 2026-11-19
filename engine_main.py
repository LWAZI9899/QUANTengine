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
from risk.pca_shock_detector import PCASystemicShockDetector
from core.dsac_gate import DSACRiskSensitiveGate
from core.synthetic_l2 import SyntheticL2Proxy
from risk.circuit_breakers import get_session_volatility_weight
from utils.web_telemetry import start_telemetry_server, latest_telemetry
from utils.markout_audit import PostTradeMarkoutAuditor

from sims.sim_monte_carlo_queue import simulate_queue_depletion
from utils.logger import logger

MAGIC_NUMBER = 234000
TARGET_VOLUME = 0.01
TAKE_PROFIT_PIPS = 6.0     # Close winning scalp slices at +6 pips
STOP_LOSS_PIPS = 8.0       # Cut losing slices at -8 pips
MAX_HOLD_SECONDS = 60.0    # Time-based exit so slices don't linger indefinitely
SESSION_START_TIME = time.time()


def pick_filling_mode(symbol: str) -> int:
    """Selects a filling mode supported by the broker symbol bitmask."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC

    if info.filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    if info.filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def clamp_volume(symbol: str, requested_volume: float) -> float:
    """Clamps volume to symbol min/max and rounds to volume_step."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return max(0.01, requested_volume)

    step = info.volume_step if info.volume_step > 0 else 0.01
    vol = max(info.volume_min, min(info.volume_max, requested_volume))
    steps = round(vol / step)
    clamped = round(steps * step, 8)
    return max(info.volume_min, clamped)


def get_closed_stats(magic: int = MAGIC_NUMBER, since_ts: float = SESSION_START_TIME):
    """Computes closed PnL and win rate from MT5 deal history for this session/magic."""
    try:
        deals = mt5.history_deals_get(since_ts, time.time() + 60.0)
        if not deals:
            return 0.0, 0.0, 0

        # Group exit/realized PnL by position_id where magic matches
        pnl_by_pos = {}
        for d in deals:
            if getattr(d, "magic", 0) != magic:
                continue
            # entry: 0=IN, 1=OUT, 2=IN/OUT, 3=OUT_BY
            entry_type = getattr(d, "entry", 0)
            if entry_type in (1, 2, 3):
                pos_id = getattr(d, "position_id", d.ticket)
                net_deal_pnl = float(d.profit) + float(getattr(d, "commission", 0.0)) + float(getattr(d, "swap", 0.0))
                pnl_by_pos[pos_id] = pnl_by_pos.get(pos_id, 0.0) + net_deal_pnl

        closed_count = len(pnl_by_pos)
        closed_pnl = sum(pnl_by_pos.values())
        wins = sum(1 for v in pnl_by_pos.values() if v > 0.0)
        win_rate = (wins / closed_count * 100.0) if closed_count > 0 else 0.0
        return float(closed_pnl), float(win_rate), int(closed_count)
    except Exception:
        return 0.0, 0.0, 0


class AsyncOrderDispatcher:
    """Non-blocking asynchronous order dispatcher supporting up to 10 orders/sec with markout auditing."""
    def __init__(self, max_concurrent=10, markout_auditor=None):
        self.queue = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.is_running = False
        self.markout_auditor = markout_auditor
        self.successful_fills = 0
        self.failed_fills = 0

    async def start_worker(self):
        self.is_running = True
        while self.is_running:
            request, future = await self.queue.get()
            try:
                result = await self.execute_order(request)
                if future and not future.done():
                    future.set_result(result)
            except Exception as e:
                logger.error(f"Async order execution failed: {e}")
                if future and not future.done():
                    future.set_exception(e)
            finally:
                self.queue.task_done()

    async def execute_order(self, request):
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, mt5.order_send, request)
        if result is None:
            err_code = mt5.last_error()
            logger.warning(f"order_send returned None. MT5 Error: {err_code}")
            self.failed_fills += 1
        elif result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.warning(f"Order rejected | retcode={result.retcode} | comment={result.comment}")
            self.failed_fills += 1
        else:
            logger.info(
                f"Order filled | ticket={result.order} | vol={result.volume} | price={result.price} | {request.get('comment', '')}"
            )
            if request.get("position") is None:
                self.successful_fills += 1
            if self.markout_auditor and request.get("position") is None:
                side = "BUY" if request.get("type") == mt5.ORDER_TYPE_BUY else "SELL"
                self.markout_auditor.register_fill(
                    order_id=result.order,
                    fill_price=result.price,
                    side=side,
                    current_time=time.time()
                )
        return result

    async def enqueue_order(self, request):
        if self.queue.qsize() < self.max_concurrent * 5:
            future = asyncio.get_running_loop().create_future()
            await self.queue.put((request, future))
            return future
        else:
            logger.warning("Order queue saturated; dropping stale slice to prevent slippage.")
            return None


async def manage_open_positions(symbol: str, bid: float, ask: float, now: float, dispatcher: AsyncOrderDispatcher):
    """Checks open positions for this symbol & magic and enqueues close orders on TP, SL, or max hold time."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    info = mt5.symbol_info(symbol)
    point = info.point if info and info.point > 0 else 0.00001
    pip_size = point * 10.0 if info and info.digits in (3, 5) else point
    filling_mode = pick_filling_mode(symbol)

    for pos in positions:
        if getattr(pos, "magic", 0) != MAGIC_NUMBER:
            continue

        age_sec = now - float(getattr(pos, "time", now))
        open_price = float(pos.price_open)

        if pos.type == mt5.ORDER_TYPE_BUY:
            pips_move = (bid - open_price) / pip_size
            close_type = mt5.ORDER_TYPE_SELL
            close_price = bid
        elif pos.type == mt5.ORDER_TYPE_SELL:
            pips_move = (open_price - ask) / pip_size
            close_type = mt5.ORDER_TYPE_BUY
            close_price = ask
        else:
            continue

        should_close = False
        reason = ""
        if pips_move >= TAKE_PROFIT_PIPS:
            should_close = True
            reason = f"TP({pips_move:+.1f}p)"
        elif pips_move <= -STOP_LOSS_PIPS:
            should_close = True
            reason = f"SL({pips_move:+.1f}p)"
        elif age_sec >= MAX_HOLD_SECONDS:
            should_close = True
            reason = f"MAX_HOLD({age_sec:.0f}s)"

        if should_close:
            close_req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(pos.volume),
                "type": close_type,
                "position": int(pos.ticket),
                "price": close_price,
                "deviation": 20,
                "magic": MAGIC_NUMBER,
                "comment": f"Close_{reason}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            await dispatcher.enqueue_order(close_req)


async def main_async():
    print("Starting Hardened QuantEngine Async Main Event Loop with Live Account & Position Telemetry...")
    symbol = "EURUSD"

    if not initialize_mt5(symbol):
        print("Initialization failed. Exiting.")
        return

    valid_lot = clamp_volume(symbol, TARGET_VOLUME)
    filling_mode = pick_filling_mode(symbol)
    print(f"Configured {symbol} execution -> volume={valid_lot}, filling_mode={filling_mode}, magic={MAGIC_NUMBER}")

    micro_engine = MicrostructureEngine(window_size=500)
    kalman_tracker = KalmanHedgeTracker(state_dim=2, process_variance=1e-5, measurement_variance=1e-3)
    les_hedger = LocalExpectedShortfallHedger(risk_aversion_q=1.5, penalty_threshold=0.0)

    dual_horizon_engine = DualHorizonEngine(base_gamma=0.1, vpin_threshold=0.60, ctox=3.0)
    markout_auditor = PostTradeMarkoutAuditor()
    dispatcher = AsyncOrderDispatcher(max_concurrent=10, markout_auditor=markout_auditor)

    hawkes_tracker = RecursiveHawkesIntensity()
    ac_slicer = AlmgrenChrissSlicer(total_shares=9.0, total_time_sec=300.0, volatility=0.015)
    rmt_denoiser = MarchenkoPasturCovarianceDenoiser(q_ratio=0.2)
    pca_detector = PCASystemicShockDetector(threshold_ratio=0.85)
    dsac_gate = DSACRiskSensitiveGate(alpha_cvar=0.05, penalty_psi=1.5)
    synthetic_l2 = SyntheticL2Proxy(window_size=50)

    worker_task = asyncio.create_task(dispatcher.start_worker())
    telemetry_task = asyncio.create_task(start_telemetry_server(port=8000))

    mid_prices = deque(maxlen=100)
    returns_history = deque(maxlen=200)
    timestamps = deque(maxlen=100)

    current_inventory_q = 0
    position_entry_timestamp = time.time()

    last_print_time = 0.0
    print_interval = 0.5

    print(f"Streaming high-frequency L1 order flow ticks for {symbol}...")

    try:
        while True:
            is_active, vol_weight = get_session_volatility_weight()
            if not is_active:
                logger.info("[Weekend Guardrail] Forex markets closed. Engine resting until Monday open.")
                await asyncio.sleep(60.0)
                continue

            tick = get_latest_tick(symbol)
            if tick:
                bid = float(tick["bid"])
                ask = float(tick["ask"])
                last = float(tick.get("last", 0.0))
                volume = float(tick.get("volume", 1.0))
                current_time = time.time()

                markout_auditor.update(current_mid=(bid + ask) / 2.0, current_time=current_time)
                await manage_open_positions(symbol=symbol, bid=bid, ask=ask, now=current_time, dispatcher=dispatcher)

                # Live Account & Open Positions Telemetry
                account_info = mt5.account_info()
                acc_balance = float(account_info.balance) if account_info else 0.0
                acc_equity = float(account_info.equity) if account_info else 0.0
                acc_margin = float(account_info.margin) if account_info else 0.0
                acc_free_margin = float(account_info.margin_free) if account_info else 0.0

                open_positions = mt5.positions_get(symbol=symbol)
                owned_positions = [p for p in open_positions if getattr(p, "magic", 0) == MAGIC_NUMBER] if open_positions else []
                open_pos_count = len(owned_positions)
                open_pos_pnl = float(sum(p.profit for p in owned_positions)) if owned_positions else 0.0
                current_inventory_q = int(round(sum(p.volume * 100.0 for p in owned_positions)))

                closed_pnl, win_rate, closed_count = get_closed_stats(magic=MAGIC_NUMBER, since_ts=SESSION_START_TIME)

                features = micro_engine.update_tick(bid=bid, ask=ask, last=last, volume=volume)

                if features:
                    current_mid = float(features["mid"])
                    current_spread = ask - bid
                    current_vpin = float(features.get("vpin", 0.35)) * vol_weight
                    current_spread_z = float(features["spread_z"])

                    micro_price = float(features.get("micro_price", current_mid))
                    if len(mid_prices) > 0 and len(timestamps) > 0:
                        dt = max(1e-3, current_time - timestamps[-1])
                        current_micro_velocity = (micro_price - mid_prices[-1]) / dt
                    else:
                        current_micro_velocity = 0.0

                    if len(mid_prices) > 0:
                        returns_history.append(current_mid - mid_prices[-1])
                    mid_prices.append(current_mid)
                    timestamps.append(current_time)

                    tfi_score = synthetic_l2.compute_tfi(
                        trade_price=last if last > 0 else current_mid,
                        trade_vol=volume,
                        bid=bid,
                        ask=ask
                    )

                    h_buy, h_sell = hawkes_tracker.update(
                        event_type=0 if current_micro_velocity > 0 else 1,
                        timestamp=current_time
                    )
                    branching_rho = float(hawkes_tracker.get_branching_spectral_radius())
                    dsac_gate.penalty_psi = 1.0 + (branching_rho * 1.2)

                    returns_arr = np.array(list(returns_history), dtype=float) if len(returns_history) > 0 else np.array([0.0])
                    std_dev_returns = float(np.std(returns_arr))

                    pc1_variance_ratio = 0.0
                    if len(returns_history) > 30 and std_dev_returns > 1e-8:
                        pca_matrix = np.column_stack([returns_arr, np.roll(returns_arr, 1), np.roll(returns_arr, 2)])
                        is_systemic_shock, pc1_variance_ratio = pca_detector.evaluate_systemic_shock(pca_matrix)
                        if is_systemic_shock:
                            logger.warning(f"[PCA Circuit Breaker] Systemic shock detected! PC1={pc1_variance_ratio*100:.1f}%. Pausing.")
                            await asyncio.sleep(1.0)
                            continue

                    if len(returns_history) > 30 and std_dev_returns > 1e-8:
                        normalized_returns = (returns_arr - np.mean(returns_arr)) / std_dev_returns
                        return_matrix = np.column_stack([normalized_returns, np.roll(normalized_returns, 1)])
                        denoised_cov = rmt_denoiser.denoise_covariance(return_matrix)
                    else:
                        denoised_cov = None

                    if len(mid_prices) > 5:
                        y_t = current_mid
                        x_t = [1.0, mid_prices[-2]]
                        kalman_res = kalman_tracker.update(y_t, x_t)
                        dynamic_beta = kalman_res["hedge_ratio"]
                    else:
                        dynamic_beta = 1.0

                    if len(mid_prices) > 10:
                        spot_arr = np.array(list(mid_prices), dtype=float)
                        gammas_arr = np.ones_like(spot_arr)
                        optimal_gamma_scale = les_hedger.optimize_hedge_gamma(
                            spot_prices=spot_arr,
                            option_gammas=gammas_arr,
                            historical_returns=returns_arr
                        )
                    else:
                        optimal_gamma_scale = 1.0

                    bid_vol_raw = float(tick.get("bid_volume", 0.0))
                    ask_vol_raw = float(tick.get("ask_volume", 0.0))
                    if bid_vol_raw > 0 and ask_vol_raw > 0:
                        vb_proxy = bid_vol_raw
                        va_proxy = ask_vol_raw
                    else:
                        imbalance_skew = max(-0.8, min(0.8, tfi_score))
                        base_vol = max(100.0, volume * 1000.0)
                        vb_proxy = base_vol * (1.0 + imbalance_skew)
                        va_proxy = base_vol * (1.0 - imbalance_skew)

                    fill_probability = float(simulate_queue_depletion(vb=vb_proxy, va=va_proxy, rho_ab=0.15, num_paths=1000))

                    active_mode = dual_horizon_engine.evaluate_entry_gate(
                        spread_z=current_spread_z,
                        vpin=current_vpin,
                        upward_prob=fill_probability,
                        branching_rho=branching_rho,
                        market_variance=std_dev_returns
                    )

                    dynamic_fill_min = 0.20 if vol_weight <= 1.0 else 0.40
                    dynamic_tfi_min = -0.80 if vol_weight <= 1.0 else -0.45

                    reward_score = 0.0
                    if active_mode in ["HFT_SCALP", "STRUCTURAL_REVERSAL"] or (vol_weight <= 1.0 and abs(tfi_score) > 0.15):
                        reward_score = float(dsac_gate.evaluate_risk_sensitive_reward(
                            delta_pnl=0.35,
                            inventory_q=current_inventory_q,
                            adverse_fill_flag=(current_vpin > 0.65),
                            fees=0.08
                        ))

                        if dsac_gate.approve_execution(reward_score) and tfi_score > dynamic_tfi_min and fill_probability >= dynamic_fill_min:
                            position_entry_timestamp = current_time

                            order_request = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": symbol,
                                "volume": valid_lot,
                                "type": mt5.ORDER_TYPE_BUY,
                                "price": ask,
                                "deviation": 20,
                                "magic": MAGIC_NUMBER,
                                "comment": f"Dyn_{active_mode}",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": filling_mode,
                            }
                            await dispatcher.enqueue_order(order_request)

                    if current_time - last_print_time >= print_interval:
                        msg = (
                            f"[{features['time'].strftime('%H:%M:%S.%f')[:-3]}] "
                            f"Mid: {current_mid:.5f} | Bal: ${acc_balance:.2f} | Eq: ${acc_equity:.2f} | "
                            f"Marg: ${acc_margin:.2f} | Open: {open_pos_count} (${open_pos_pnl:+.2f}) | "
                            f"ClosedPnL: ${closed_pnl:+.2f} | Fills: {dispatcher.successful_fills} | WinRate: {win_rate:.1f}%"
                        )
                        print(msg)
                        logger.info(msg)
                        last_print_time = current_time

                    latest_telemetry.update({
                        "timestamp": features["time"].strftime("%H:%M:%S.%f")[:-3],
                        "symbol": symbol,
                        "mid": float(current_mid),
                        "spread": float(current_spread),
                        "vol_weight": float(vol_weight),
                        "balance": float(acc_balance),
                        "equity": float(acc_equity),
                        "margin": float(acc_margin),
                        "free_margin": float(acc_free_margin),
                        "open_positions": int(open_pos_count),
                        "open_pnl": float(open_pos_pnl),
                        "closed_pnl": float(closed_pnl),
                        "closed_trades": int(closed_count),
                        "win_rate": float(win_rate),
                        "fills": int(dispatcher.successful_fills),
                        "successful_fills": int(dispatcher.successful_fills),
                        "mode": active_mode,
                        "tfi": float(tfi_score),
                        "vpin": float(current_vpin),
                        "hawkes_rho": float(branching_rho),
                        "fill_prob": float(fill_probability * 100.0),
                        "vb_proxy": float(vb_proxy),
                        "va_proxy": float(va_proxy),
                        "dsac_reward": float(reward_score),
                        "cvar_penalty": float(dsac_gate.penalty_psi),
                        "markout_1s": 0.0,
                        "markout_5s": 0.0,
                        "mid_history": list(mid_prices)[-40:],
                        "time_history": [f"T-{i}" for i in range(len(list(mid_prices)[-40:]), 0, -1)]
                    })

            await asyncio.sleep(0.01)

    except asyncio.CancelledError:
        print("Async event loop cancelled.")
    finally:
        dispatcher.is_running = False
        worker_task.cancel()
        telemetry_task.cancel()
        mt5.shutdown()
        print(f"\nEngine safely shut down. Total successful fills: {dispatcher.successful_fills}")


if __name__ == "__main__":
    asyncio.run(main_async())