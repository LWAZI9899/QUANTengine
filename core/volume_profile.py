import numpy as np

def compute_volume_profile(prices, volumes, bins=50):
    """Computes Point of Control (POC) and Value Area High/Low (VAH/VAL)."""
    if len(prices) == 0:
        return None, None, None
        
    hist, bin_edges = np.histogram(prices, bins=bins, weights=volumes)
    poc_idx = np.argmax(hist)
    poc = (bin_edges[poc_idx] + bin_edges[poc_idx+1]) / 2.0
    
    total_vol = np.sum(hist)
    sorted_indices = np.argsort(hist)[::-1]
    
    accumulated_vol = 0.0
    valuable_bins = []
    for idx in sorted_indices:
        accumulated_vol += hist[idx]
        valuable_bins.append(idx)
        if accumulated_vol >= 0.70 * total_vol:
            break
            
    valuable_prices = [bin_edges[i] for i in valuable_bins]
    return poc, min(valuable_prices), max(valuable_prices)