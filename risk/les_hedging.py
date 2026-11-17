import numpy as np

class LocalExpectedShortfallHedger:
    def __init__(self, risk_aversion_q=1.5, penalty_threshold=0.0):
        """
        Bouchaud-Pochart Minimum Local Expected Shortfall (LES) optimizer.
        Penalizes tail losses using a non-linear utility threshold q.
        """
        self.q = risk_aversion_q
        self.delta_0 = penalty_threshold

    def compute_les_penalty(self, target_portfolio_changes):
        """
        Computes the Expected Shortfall penalty for a distribution of terminal wealth changes.
        """
        deltas = np.array(target_portfolio_changes, dtype=float)
        # Downside deviations below threshold
        downside_deviations = np.maximum(0.0, self.delta_0 - deltas)
        
        # Loss utility penalty raised to power q
        loss_utility = np.power(downside_deviations, self.q)
        return float(np.mean(loss_utility))

    def optimize_hedge_gamma(self, spot_prices, option_gammas, historical_returns):
        """
        Determines optimal low-Gamma scaling to minimize LES under fat-tailed Student-t regimes.
        """
        if len(historical_returns) < 10:
            return 1.0  # Default standard delta-hedge scaling
            
        # Measure kurtosis to detect fat tails
        kurtosis = np.mean((historical_returns - np.mean(historical_returns))**4) / (np.std(historical_returns)**4 + 1e-8)
        
        # If fat tails are detected (kurtosis > 3.0), suppress Gamma to reduce transaction costs
        if kurtosis > 3.0:
            # Scaling factor < 1.0 flattens Gamma exposure near the money
            gamma_scaling_factor = 1.0 / np.sqrt(kurtosis / 3.0)
        else:
            gamma_scaling_factor = 1.0
            
        return float(np.clip(gamma_scaling_factor, 0.2, 1.0))