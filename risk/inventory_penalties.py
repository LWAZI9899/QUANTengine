import numpy as np

def calculate_reservation_price(mid_price: float, inventory_q: int, gamma: float, volatility: float, time_to_close: float) -> float:
    """
    Calculates the Avellaneda-Stoikov reservation price R(s, q, t).
    """
    variance_term = (volatility ** 2) * time_to_close
    reservation_price = mid_price - (inventory_q * gamma * variance_term)
    return float(reservation_price)