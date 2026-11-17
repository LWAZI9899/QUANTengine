import numpy as np


class SyntheticL2Proxy:
  """Reconstructs L2-equivalent order book pressure from L1 quotes and trade tapes

  using Order Flow Imbalance (OFI) and Trade-Flow Imbalance (TFI).
  """

  def __init__(self, window_size: int = 50):
    self.window_size = window_size
    self.signed_volumes = []
    self.last_mid = None

  def compute_ofi_increment(
      self,
      pb_curr: float,
      pb_prev: float,
      vb_curr: float,
      vb_prev: float,
      pa_curr: float,
      pa_prev: float,
      va_curr: float,
      va_prev: float,
  ) -> float:
    """Calculates Cont-Kukanov-Stoikov Order Flow Imbalance (OFI)."""
    # Bid side OFI contribution
    if pb_curr > pb_prev:
      ofi_b = vb_curr
    elif pb_curr == pb_prev:
      ofi_b = vb_curr - vb_prev
    else:
      ofi_b = -vb_prev

    # Ask side OFI contribution
    if pa_curr < pa_prev:
      ofi_a = -va_curr
    elif pa_curr == pa_prev:
      ofi_a = -(va_curr - va_prev)
    else:
      ofi_a = va_prev

    return float(ofi_b -ofi_a)

  def compute_tfi(self, trade_price: float, trade_vol: float, bid: float, ask: float) -> float:
    """Computes Trade-Flow Imbalance (TFI) using the Lee-Ready rule."""
    mid = (bid + ask) / 2.0
    if self.last_mid is None:
      self.last_mid = mid

    # Lee-Ready trade classification
    if trade_price > mid:
      sign = 1.0
    elif trade_price < mid:
      sign = -1.0
    else:
      sign = 1.0 if mid >= self.last_mid else -1.0

    self.last_mid = mid
    self.signed_volumes.append(sign * trade_vol)

    if len(self.signed_volumes) > self.window_size:
      self.signed_volumes.pop(0)

    total_vol = sum(abs(v) for v in self.signed_volumes)
    if total_vol <= 0:
      return 0.0

    net_signed_vol = sum(self.signed_volumes)
    return float(net_signed_vol / total_vol)