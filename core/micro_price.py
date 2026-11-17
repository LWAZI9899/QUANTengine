from utils.fallbacks import safe_divide

def compute_micro_price(bid, ask, bid_vol, ask_vol):
    """Calculates Stoikov L1 Micro-Price using safe fallback division."""
    total_vol = bid_vol + ask_vol
    weighted_sum = (bid_vol * ask) + (ask_vol * bid)
    return safe_divide(weighted_sum, total_vol, fallback=(bid + ask) / 2.0)