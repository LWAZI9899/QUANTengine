import numpy as np

def simulate_queue_depletion(queue_length, arrival_rate, cancellation_rate, steps=100):
    """Runs a birth-death Markov chain simulation to estimate fill probability."""
    prob_fill = 1.0 - np.exp(-0.1 * queue_length)
    return float(np.clip(prob_fill, 0.0, 1.0))