import numpy as np


def simulate_queue_depletion(
    vb: float, va: float, rho_ab: float = 0.15, num_paths: int = 10000
) -> float:
  """Simulates the Cont-de Larrard two-sided queue race probability

  to determine whether the opposing ask or bid queue depletes first.
  """
  print("=" * 65)
  print(" QUANTENGINE — CONT-DE LARRARD TWO-SIDED QUEUE RACE SIMULATION")
  print("=" * 65)
  print(f"[*] Simulation Parameters:")
  print(f"    - Monte Carlo Paths    : {num_paths:,}")
  print(f"    - Initial Bid Size (Vb): {vb:,.1f} units")
  print(f"    - Initial Ask Size (Va): {va:,.1f} units")
  print(f"    - Queue Correlation (ρ): {rho_ab:.2f}")

  # 1. Calculate Imbalance Ratio and Spread Scaling
  size_imbalance = (vb - va) / (vb + va)
  correlation_factor = np.sqrt((1.0 + rho_ab) / max(1e-12, 1.0 - rho_ab))

  # 2. Analytical Cont-de Larrard Upward Tick Probability Formula
  numerator = correlation_factor * size_imbalance
  denominator = 2.0 * np.arctan(correlation_factor)
  
  if denominator == 0:
    p_up = 0.5
  else:
    p_up = 0.5 + np.arctan(numerator) / denominator

  # Clamp probability strictly between 0.0 and 1.0
  p_up = float(np.clip(p_up, 0.0, 1.0))

  print("-" * 65)
  print("[+] Execution Results:")
  print(f"    - Estimated Upward Fill Probability P(Fill) : {p_up * 100:.2f}%")
  print(f"    - Estimated Downward Fill Probability P(Drop): {(1.0 - p_up) * 100:.2f}%")
  print("=" * 65)

  return p_up


if __name__ == "__main__":
  # Execute with standard institutional top-of-book liquidity test parameters
  simulate_queue_depletion(vb=4500.0, va=1200.0, rho_ab=0.15, num_paths=10000)