import numpy as np


class RecursiveHawkesIntensity:
    """O(1) Recursive 2x2 Hawkes Point Process Intensity Tracker with dynamic branching estimation."""

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
        self._current_rho = 0.5  # Dynamic dynamic tracking cache

    def update(self, event_type: int, timestamp: float) -> tuple[float, float]:
        """Updates recursive accumulators and returns instantaneous intensities."""
        if self.last_timestamp is None:
            dt = 0.01
        else:
            dt = max(1e-4, timestamp - self.last_timestamp)
        self.last_timestamp = timestamp

        # 1. Analytical decay between events with clamping for numerical stability
        decay_factors = np.exp(-self.beta * min(dt, 5.0))
        self.R *= decay_factors

        # 2. Jump increment upon new event arrival (0 for Buy, 1 for Sell)
        if event_type in [0, 1]:
            for i in range(2):
                self.R[i, event_type] += self.beta[i, event_type]
                
            # Dynamically adapt self-excitation alpha slightly based on arrival velocity (burst detection)
            if dt < 0.05:  # Rapid consecutive ticks indicate clustering
                self.alpha = np.clip(self.alpha * 1.01, 0.1, 0.85)
            else:
                self.alpha = np.clip(self.alpha * 0.99, 0.1, 0.85)

        # 3. Compute current intensities
        lambdas = np.zeros(2)
        for i in range(2):
            sum_excitation = np.sum(self.alpha[i, :] * self.R[i, :])
            lambdas[i] = self.mu[i] + sum_excitation

        # Update cached spectral radius
        G = self.alpha / self.beta
        eigenvalues = np.linalg.eigvals(G)
        self._current_rho = float(np.max(np.abs(eigenvalues)))

        return float(lambdas[0]), float(lambdas[1])

    def get_branching_spectral_radius(self) -> float:
        """Computes dynamic spectral radius rho(G) to gauge true market fragility."""
        return self._current_rho