import pytest
from sims.sim_monte_carlo_queue import simulate_queue_depletion

def test_analytical_queue_depletion_probability():
    # Test high bid volume vs low ask volume (favorable fill probability)
    p_up = simulate_queue_depletion(vb=4500.0, va=1200.0, rho_ab=0.15, num_paths=1000)
    
    assert 0.0 <= p_up <= 1.0
    assert p_up > 0.70  # Should comfortably clear institutional execution threshold