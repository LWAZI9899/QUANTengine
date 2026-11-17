def compute_reservation_price(mid, inventory, risk_aversion=0.1, volatility=0.015, time_horizon=1.0):
    """Computes Avellaneda-Stoikov HJB reservation price adjusting for inventory skew."""
    return mid - (inventory * risk_aversion * (volatility ** 2) * time_horizon)