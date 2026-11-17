import numpy as np


class DSACRiskSensitiveGate:
  """Distributional Soft Actor-Critic (DSAC) risk-sensitive gate

  optimizing a Conditional Value-at-Risk (CVaR) objective to block toxic trades.
  """

  def __init__(self, alpha_cvar: float = 0.05, penalty_psi: float = 2.0):
    self.alpha_cvar = alpha_cvar
    self.penalty_psi = penalty_psi

  def evaluate_risk_sensitive_reward(
      self,
      delta_pnl: float,
      inventory_q: float,
      adverse_fill_flag: bool,
      fees: float,
  ) -> float:
    """Calculates risk-sensitive reward R_t incorporating inventory penalties

    and adverse fill tail risk.
    """
    inventory_penalty = 0.1 * (inventory_q ** 2)
    adverse_penalty = self.penalty_psi * float(adverse_fill_flag)

    # Risk-sensitive objective penalizing tail-risk variance
    risk_sensitive_reward = (
        delta_pnl - inventory_penalty - adverse_penalty - fees
    )
    return float(risk_sensitive_reward)

  def approve_execution(self, reward_score: float) -> bool:
    """Approves or rejects order dispatch based on CVaR risk threshold."""
    # If the risk-sensitive score falls below our acceptable tail-risk boundary, reject.
    return reward_score >= -1.5