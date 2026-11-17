import numpy as np

def compute_parametric_var(returns, confidence_level=0.99):
    """Computes parametric Value-at-Risk from tick return series."""
    if len(returns) < 10:
        return 0.0
    mean = np.mean(returns)
    std = np.std(returns)
    from scipy.stats import norm
    z_score = norm.ppf(1.0 - confidence_level)
    return float(-(mean + z_score * std))