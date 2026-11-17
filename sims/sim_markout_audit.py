import numpy as np

def audit_markout(fill_price, future_prices):
    """Calculates post-trade execution slippage against future midprice markouts."""
    if not future_prices:
        return 0.0
    return float(np.mean(future_prices) - fill_price)