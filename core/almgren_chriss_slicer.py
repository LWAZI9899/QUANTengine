import numpy as np


class AlmgrenChrissSlicer:
  """Computes optimal multi-slice liquidation or accumulation trajectories

  using the Almgren-Chriss hyperbolic sine formulation.
  """

  def __init__(
      self,
      total_shares: float,
      total_time_sec: float,
      volatility: float,
      lambda_risk: float = 2.5e-8,
      eta_temp: float = 1.5e-6,
  ):
    self.X0 = total_shares
    self.T = total_time_sec
    self.sigma = volatility
    self.lambda_risk = lambda_risk
    self.eta_temp = eta_temp

    # Compute urgency parameter kappa_AC
    self.kappa_ac = np.sqrt(
        (self.lambda_risk * (self.sigma ** 2)) / max(1e-12, self.eta_temp)
    )

  def get_target_position(self, elapsed_sec: float) -> float:
    """Returns the optimal remaining inventory target x*(t) at elapsed time t."""
    t = min(max(0.0, elapsed_sec), self.T)
    if self.kappa_ac * self.T == 0:
      return self.X0 * (1.0 - t / self.T)

    numerator = np.sinh(self.kappa_ac * (self.T - t))
    denominator = np.sinh(self.kappa_ac * self.T)
    if denominator == 0:
      return 0.0
    return float(self.X0 * (numerator / denominator))

  def get_slice_size(self, current_inventory: float, elapsed_sec: float, dt: float) -> float:
    """Calculates the exact clip size to execute in current time step dt."""
    target_inventory = self.get_target_position(elapsed_sec + dt)
    slice_delta = target_inventory - current_inventory
    return float(slice_delta)