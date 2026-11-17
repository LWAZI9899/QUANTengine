import numpy as np


class DualHorizonRegimeEngine:
  """Controls dynamic toggling between HFT scalps and structural reversals with institutional gates."""

  def __init__(
      self,
      base_gamma: float = 0.1,
      vpin_threshold: float = 0.55,
      ctox: float = 3.0,
  ):
    self.base_gamma = base_gamma
    self.vpin_threshold = vpin_threshold
    self.ctox = ctox

  def compute_effective_gamma(self, current_vpin: float) -> float:
    """Calculates VPIN-modulated exponential risk aversion[cite: 1]."""
    toxicity_excess = max(0.0, current_vpin - self.vpin_threshold)
    return float(self.base_gamma * np.exp(self.ctox * toxicity_excess))

  def evaluate_entry_gate(
      self,
      spread_z: float,
      vpin: float,
      upward_prob: float,
      branching_rho: float,
  ) -> str:
    """Evaluates whether market conditions meet institutional thresholds for high win-rate entry."""
    # Circuit breaker override for extreme endogenous fragility
    if branching_rho > 0.95:
      return "CIRCUIT_BREAKER_HALT"

    # Toxicity cutoff
    if vpin > 0.70:
      return "TOXIC_FLOW_BLOCK"

    # Structural Reversal Trigger (Oversold/Overbought extreme with high queue probability)
    if abs(spread_z) >= 8.0 and upward_prob >= 0.70:
      return "STRUCTURAL_REVERSAL"

    # HFT Scalp Trigger
    if abs(spread_z) >= 4.0 and upward_prob >= 0.65:
      return "HFT_SCALP"

    return "DORMANT"