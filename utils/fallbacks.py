import numpy as np

def safe_divide(numerator, denominator, fallback=0.0):
    """Fallback logic wrapper to prevent ZeroDivisionError during thin liquidity."""
    try:
        if denominator == 0 or np.isnan(denominator) or np.isnan(numerator):
            return fallback
        return numerator / denominator
    except Exception:
        return fallback