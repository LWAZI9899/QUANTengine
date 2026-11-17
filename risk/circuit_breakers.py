def check_circuit_breakers(spread_z, vpin_score, max_spread_z=3.0, max_vpin=0.65):
    """Enforces safety guardrails against wide spreads and toxic order flow."""
    if spread_z > max_spread_z:
        return False, "HALT: Spread Z-score exceeded threshold (Liquidity withdrawal)"
    if vpin_score > max_vpin:
        return False, "HALT: VPIN toxicity exceeded threshold (Informed adverse flow)"
    return True, "OK"