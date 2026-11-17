import time
from collections import deque
from core.ingestion_feeder import initialize_mt5, get_latest_tick
from core.microstructure_engine import MicrostructureEngine
from core.kalman_hedge import KalmanHedgeTracker
from risk.les_hedging import LocalExpectedShortfallHedger
from utils.logger import logger

def main():
    print("Starting QuantEngine Main Event Loop with Kalman & LES Hedging Pipelines...")
    symbol = "EURUSD"
    
    if not initialize_mt5(symbol):
        print("Initialization failed. Exiting.")
        return

    # 1. Instantiate Core & Advanced Quantitative Engines
    micro_engine = MicrostructureEngine(window_size=500)
    kalman_tracker = KalmanHedgeTracker(state_dim=2, process_variance=1e-5, measurement_variance=1e-3)
    les_hedger = LocalExpectedShortfallHedger(risk_aversion_q=1.5, penalty_threshold=0.0)

    # Rolling buffer for returns calculation (needed for LES fat-tail detection)
    mid_prices = deque(maxlen=100)

    print(f"Streaming live institutional metrics with real-time risk tracking for {symbol}...")

    try:
        while True:
            tick = get_latest_tick(symbol)
            if tick:
                bid = tick['bid']
                ask = tick['ask']
                last = tick.get('last', 0.0)
                volume = tick.get('volume', 1.0)

                # 2. Pass live L1 data through microstructure buffer
                features = micro_engine.update_tick(bid=bid, ask=ask, last=last, volume=volume)
                
                if features:
                    current_mid = features['mid']
                    mid_prices.append(current_mid)

                    # 3. Update Kalman Filter Hedge Ratio (using synthetic second asset or lagged mid as regressor)
                    if len(mid_prices) > 5:
                        y_t = current_mid
                        x_t = [1.0, mid_prices[-2]]  # Regressing current mid against previous mid/benchmark
                        kalman_res = kalman_tracker.update(y_t, x_t)
                        dynamic_beta = kalman_res['hedge_ratio']
                    else:
                        dynamic_beta = 1.0

                    # 4. Compute Tail-Risk LES Gamma Scaling if we have enough returns
                    if len(mid_prices) > 10:
                        returns = list(mid_prices)
                        optimal_gamma_scale = les_hedger.optimize_hedge_gamma(
                            spot_prices=list(mid_prices), 
                            option_gammas=[1.0]*len(mid_prices), 
                            historical_returns=returns
                        )
                    else:
                        optimal_gamma_scale = 1.0

                    # 5. Log Unified Institutional State
                    msg = (
                        f"[{features['time'].strftime('%H:%M:%S.%f')[:-3]}] "
                        f"Mid: {current_mid:.5f} | "
                        f"MicroPrice: {features['micro_price']:.5f} | "
                        f"SpreadZ: {features['spread_z']:.2f} | "
                        f"Kalman Beta: {dynamic_beta:.4f} | "
                        f"LES Gamma Scale: {optimal_gamma_scale:.2f}"
                    )
                    print(msg)
                    logger.info(msg)
                    
            # High-frequency polling interval
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nShutting down engine safely...")

if __name__ == "__main__":
    main()