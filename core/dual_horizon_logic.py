import numpy as np

class DualHorizonEngine:
    def __init__(self, risk_pct=0.01):
        self.risk_pct = risk_pct
        self.mode = "HFT_SCALP"  # Default starting mode

    def evaluate_market_regime(self, vpin: float, spread_z: float, micro_velocity: float) -> str:
        """
        Switches execution horizon based on order flow toxicity (VPIN) and structural momentum.
        """
        # Clean structural imbalance detected -> Switch to Structural Reversal Mode
        if abs(spread_z) > 8.0 and vpin < 0.40:
            self.mode = "STRUCTURAL_REVERSAL"
        # High toxicity or flat momentum -> Revert to Ultra-Fast HFT Scalp Mode
        elif vpin > 0.65 or abs(micro_velocity) < 0.1:
            self.mode = "HFT_SCALP"
            
        return self.mode

    def calculate_optimal_holding_horizon(self, volatility: float, vpin: float, inventory_q: int, gamma: float) -> float:
        """
        Computes the stochastic optimal holding horizon based on inventory penalty 
        and volatility decay rather than an arbitrary clock time.
        """
        # Base holding time scaled inversely by volatility and risk aversion (gamma)
        safe_gamma = max(gamma, 0.01)
        base_horizon = 60.0 / (volatility * safe_gamma)
        
        # Compress the horizon if VPIN toxicity spikes (emergency exit acceleration)
        toxicity_penalty = max(1.0, vpin * 3.0)
        
        # Adjust for inventory weight (heavier inventory exits faster)
        inventory_factor = 1.0 + (abs(inventory_q) * 0.1)
        
        optimal_seconds = (base_horizon / toxicity_penalty) / inventory_factor
        
        # Clamp between ultra-fast HFT bounds (10s) and max structural cap (900s)
        return float(np.clip(optimal_seconds, 10.0, 900.0))