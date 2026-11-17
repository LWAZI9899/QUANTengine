import numpy as np

def compute_ofi(bid_curr, bid_prev, ask_curr, ask_prev, bid_vol_curr, bid_vol_prev, ask_vol_curr, ask_vol_prev):
    """Calculates Order Flow Imbalance (Cont et al.) across L1 updates."""
    bid_contrib = np.where(bid_curr >= bid_prev, bid_vol_curr, 0) - np.where(bid_curr <= bid_prev, bid_vol_prev, 0)
    ask_contrib = np.where(ask_curr <= ask_prev, ask_vol_curr, 0) - np.where(ask_curr >= ask_prev, ask_vol_prev, 0)
    return float(bid_contrib - ask_contrib)

def compute_lee_ready_sign(trade_price, mid_price, prev_trade_price, prev_prev_trade_price):
    """Two-stage Lee-Ready trade classification rule against midprice and tick test."""
    if trade_price > mid_price:
        return 1.0
    elif trade_price < mid_price:
        return -1.0
    else:
        # Fallback to tick test rule
        if prev_trade_price > prev_prev_trade_price:
            return 1.0
        elif prev_trade_price < prev_prev_trade_price:
            return -1.0
        return 0.0