import numpy as np


class RecursiveHawkesIntensity:
  """O(1) Recursive 2x2 Hawkes Point Process Intensity Tracker."""

  def __init__(
      self,
      baseline_mu: float = 0.1,
      alpha: float = 0.4,
      beta: float = 0.8,
  ):
    self.mu = np.array([baseline_mu, baseline_mu])
    self.alpha = np.array([[alpha, 0.2], [0.2, alpha]])
    self.beta = np.array([[beta, beta], [beta, beta]])
    self.R = np.zeros((2, 2))
    self.last_timestamp = None

  def update(self, event_type: int, timestamp: float) -> tuple[float, float]:
    """Updates recursive accumulators and returns instantaneous intensities."""
    if self.last_timestamp is None:
      dt = 0.01
    else:
      dt = max(1e-4, timestamp - self.last_timestamp)
    self.last_timestamp = timestamp

    for i in range(2):
      for j in range(2):
        self.R[i, j] *= np.exp(-self.beta[i, j] * dt)

    if event_type in [0, 1]:
      for i in range(2):
        self.R[i, event_type] += self.beta[i, event_type]

    lambdas = np.zeros(2)
    for i in range(2):
      sum_excitation = sum(self.alpha[i, j] * self.R[i, j] for j in range(2))
      lambdas[i] = self.mu[i] + sum_excitation

    return float(lambdas[0]), float(lambdas[1])

  def get_branching_spectral_radius(self) -> float:
    """Computes spectral radius rho(G) to gauge market fragility."""
    G = self.alpha / self.beta
    eigenvalues = np.linalg.eigvals(G)
    return float(np.max(np.abs(eigenvalues)))