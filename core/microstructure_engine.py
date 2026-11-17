import numpy as np
import pandas as pd
from collections import deque

class MicrostructureEngine:
    def __init__(self, window_size=500):
        self.window_size = window_size
        self.tick_buffer = deque(maxlen=window_size)
        
    def update_tick(self, bid, ask, last, volume):
        """Ingests a new L1 tick and updates internal ring buffers."""
        timestamp = pd.Timestamp.now()
        mid = (bid + ask) / 2.0
        spread = ask - bid
        
        tick_data = {
            "time": timestamp,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": spread,
            "last": last,
            "volume": volume
        }
        self.tick_buffer.append(tick_data)
        return self._compute_features()

    def _compute_features(self):
        """Computes rolling institutional proxies from the tick buffer in O(1) memory."""
        if len(self.tick_buffer) < 2:
            return None
            
        df = pd.DataFrame(self.tick_buffer)
        
        # 1. Spread Z-Score
        spread_mean = df["spread"].rolling(window=min(len(df), 100), min_periods=1).mean().iloc[-1]
        spread_std = df["spread"].rolling(window=min(len(df), 100), min_periods=1).std().iloc[-1]
        spread_z = (df["spread"].iloc[-1] - spread_mean) / (spread_std if spread_std > 0 else 1e-6)
        
        # 2. Lee-Ready / Mid-Change Trade Direction Rule
        dm = df["mid"].diff().iloc[-1]
        trade_sign = np.sign(dm) if dm != 0 else 0.0
        
        # 3. Stoikov Micro-Price Proxy (L1 weight approximation)
        current_mid = df["mid"].iloc[-1]
        micro_price = current_mid + (0.5 * trade_sign * df["spread"].iloc[-1])
        
        return {
            "time": df["time"].iloc[-1],
            "mid": current_mid,
            "spread": df["spread"].iloc[-1],
            "spread_z": spread_z,
            "trade_sign": trade_sign,
            "micro_price": micro_price
        }