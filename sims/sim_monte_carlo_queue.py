import numpy as np

def simulate_queue_depletion(
    vb: float, va: float, rho_ab: float = 0.15, num_paths: int = 1000
) -> float:
    """Computes the analytical Cont-de Larrard two-sided queue race probability

    silently in the background for high-frequency tick processing.
    """
    total_vol = vb + va
    if total_vol <= 0:
        return 0.5

    size_imbalance = (vb - va) / total_vol
    correlation_factor = np.sqrt((1.0 + rho_ab) / max(1e-12, 1.0 - rho_ab))

    numerator = correlation_factor * size_imbalance
    denominator = 2.0 * np.arctan(correlation_factor)
    
    if denominator == 0:
        p_up = 0.5
    else:
        p_up = 0.5 + np.arctan(numerator) / denominator

    return float(np.clip(p_up, 0.0, 1.0))