import pytest
import numpy as np
from core.microstructure_engine import MicrostructureEngine
from core.synthetic_l2 import SyntheticL2Proxy

def test_microstructure_engine_metrics():
    engine = MicrostructureEngine(window_size=100)
    # Feed mock tick data
    features = engine.update_tick(bid=1.1000, ask=1.1002, last=1.1001, volume=5.0)
    
    assert features is not None
    assert 'mid' in features
    assert 'spread' in features
    assert 'micro_price' in features
    assert features['mid'] == pytest.approx(1.1001)

def test_synthetic_l2_tfi():
    proxy = SyntheticL2Proxy(window_size=10)
    # Aggressive buyer print above mid
    tfi = proxy.compute_tfi(trade_price=1.1003, trade_vol=15.0, bid=1.1000, ask=1.1001)
    assert tfi > 0.0