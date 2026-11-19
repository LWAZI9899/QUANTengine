import time
from collections import deque
from utils.logger import logger

class PostTradeMarkoutAuditor:
    """Tracks midprice markouts at 1s, 5s, and 30s post-fill to audit execution drag and adverse selection."""
    def __init__(self):
        self.pending_audits = deque()

    def register_fill(self, order_id: int, fill_price: float, side: str, current_time: float):
        """Registers a newly filled order for longitudinal markout tracking."""
        self.pending_audits.append({
            "order_id": order_id,
            "fill_price": fill_price,
            "side": side.upper(),
            "entry_time": current_time,
            "milestones": {1.0: None, 5.0: None, 30.0: None}
        })

    def update(self, current_mid: float, current_time: float):
        """Evaluates pending markout timers on every tick."""
        for audit in list(self.pending_audits):
            elapsed = current_time - audit["entry_time"]
            side_multiplier = 1.0 if audit["side"] == "BUY" else -1.0
            
            for target_sec in [1.0, 5.0, 30.0]:
                if audit["milestones"][target_sec] is None and elapsed >= target_sec:
                    price_delta = (current_mid - audit["fill_price"]) * side_multiplier
                    audit["milestones"][target_sec] = price_delta
                    logger.info(
                        f"[Markout Audit] Order {audit['order_id']} ({audit['side']}) "
                        f"@ {target_sec}s Markout Delta: {price_delta:+.5f} Pips"
                    )

            # Purge audit record once 30-second window completes
            if elapsed > 30.0:
                self.pending_audits.remove(audit)