import pytest
import numpy as np
from risk.dsac_gate import DSACRiskSensitiveGate
from risk.rmt_covariance import MarchenkoPasturCovarianceDenoiser
from risk.les_hedging import LocalExpectedShortfallHedger

def test_dsac_gate_approval():
    gate = DSACRiskSensitiveGate(alpha_cvar=0.05, penalty_psi=2.0)
    reward = gate.evaluate_risk_sensitive_reward(
        delta_pnl=0.50, inventory_q=1, adverse_fill_flag=False, fees=0.05
    )
    assert gate.approve_execution(reward) is True

def test_rmt_covariance_denoising():
    denoiser = MarchenkoPasturCovarianceDenoiser(q_ratio=0.2)
    # Generate random return matrix
    np.random.seed(42)
    returns_matrix = np.random.normal(0, 0.01, size=(50, 5))
    denoised_cov = denoiser.denoise_covariance(returns_matrix)
    
    assert denoised_cov is not None
    assert denoised_cov.shape == (5, 5)

def test_les_hedging_gamma_scaling():
    hedger = LocalExpectedShortfallHedger(risk_aversion_q=1.5, penalty_threshold=0.0)
    spots = np.array([1.10, 1.101, 1.102, 1.103, 1.104, 1.105, 1.106, 1.107, 1.108, 1.109, 1.110])
    gammas = np.ones_like(spots)
    returns = np.array([0.001, -0.0005, 0.0002, 0.001, -0.0001])
    
    scale = hedger.optimize_hedge_gamma(spot_prices=spots, option_gammas=gammas, historical_returns=returns)
    assert isinstance(scale, float)
    assert scale > 0.0