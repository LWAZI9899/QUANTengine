from datetime import datetime, timezone
import pytz
import logging

logger = logging.getLogger("QuantEngine")


def get_session_volatility_weight() -> tuple[bool, float]:
  """Evaluates current session time to run 24/7 while returning a dynamic

  volatility scaling factor for high-vol vs low-vol sessions.
  """
  utc_now = datetime.now(timezone.utc)
  sast_tz = pytz.timezone("Africa/Johannesburg")
  sast_now = utc_now.astimezone(sast_tz)

  current_hour = sast_now.hour
  weekday = sast_now.weekday()

  # Weekend check (Forex markets closed on Saturdays and Sundays)
  if weekday >= 5:
    return False, 0.0

  # Peak London / New York Overlap (15:00 - 17:00 SAST / 13:00 - 15:00 UTC)
  if 15 <= current_hour < 17:
    return True, 1.0  # Full volume weight (strict standard thresholds)

  # Asian Session / Low Liquidity Rollover Hours (e.g., 01:00 - 08:00 SAST)
  elif 1 <= current_hour < 8:
    # Allow trading, but apply a higher toxicity penalty multiplier due to wider spreads
    return True, 1.8

  # Default Active Sessions (London open, New York afternoon, European sessions)
  else:
    return True, 1.2