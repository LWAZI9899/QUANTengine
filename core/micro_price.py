import numpy as np


def compute_micro_price(bid: float, ask: float, bid_vol: float, ask_vol: float) -> float:
  """Computes Stoikov's top-of-book micro-price."""
  total_vol = bid_vol + ask_vol
  if total_vol <= 0:
    return (bid + ask) / 2.0
  return (bid_vol * ask + ask_vol * bid) / total_vol


def compute_cont_de_larrard_probability(
    bid_vol: float, ask_vol: float, rho_ab: float = 0.1
) -> float:
  """Calculates Cont-de Larrard analytical upward tick probability."""
  denominator = bid_vol + ask_vol
  if denominator <= 0:
    return 0.5
  vol_imbalance = (bid_vol - ask_vol) / denominator
  skew_factor = np.sqrt((1.0 + rho_ab) / max(1e-4, 1.0 - rho_ab))
  argument = skew_factor * vol_imbalance
  arctan_val = np.arctan(argument)
  max_arctan = np.arctan(skew_factor)
  if max_arctan <= 0:
    return 0.5
  return float(0.5 + 0.5 * (arctan_val / max_arctan))


class KylesLambdaEstimator:
  """Estimates Kyle's Lambda (permanent price impact per unit of signed volume)[cite: 1]."""

  def __init__(self, window_size: int = 50):
    self.window_size = window_size
    self.signed_volumes = []
    self.mid_price_changes = []

  def update(self, signed_volume: float, mid_price_change: float) -> float:
    self.signed_volumes.append(signed_volume)
    self.mid_price_changes.append(mid_price_change)

    if len(self.signed_volumes) > self.window_size:
      self.signed_volumes.pop(0)
      self.mid_price_changes.pop(0)

    if len(self.signed_volumes) < 5:
      return 0.0

    x = np.array(self.signed_volumes)
    y = np.array(self.mid_price_changes)
    denom = np.sum(x ** 2)
    if denom <= 0:
      return 0.0
    return float(np.sum(x * y) / denom)