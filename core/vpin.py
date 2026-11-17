import numpy as np
from scipy.stats import norm
from utils.fallbacks import safe_divide

def compute_vpin(bucket_prices, bucket_volumes, sigma, bucket_size=200):
    """Calculates Volume-Synchronized Probability of Informed Trading (VPIN)."""
    if len(bucket_prices) < 2:
        return 0.0
    
    dp = np.diff(bucket_prices)
    norm_cdf = norm.cdf(safe_divide(dp, sigma, fallback=0.0))
    buy_vol = bucket_size * norm_cdf
    sell_vol = bucket_size * (1.0 - norm_cdf)
    
    imbalance = np.abs(buy_vol - sell_vol)
    total_volume_window = len(bucket_prices) * bucket_size
    return safe_divide(np.sum(imbalance), total_volume_window, fallback=0.0)