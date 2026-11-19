import MetaTrader5 as mt5

# Optional: set this if mt5.initialize() hangs trying to locate/launch the terminal
MT5_PATH = None  # e.g. r"C:\Program Files\MetaTrader 5\terminal64.exe"


def pick_filling_mode(symbol: str):
  """Selects a filling mode supported by the broker symbol."""
  info = mt5.symbol_info(symbol)
  if info is None:
    return mt5.ORDER_FILLING_IOC

  if info.filling_mode & 1:
    return mt5.ORDER_FILLING_FOK
  if info.filling_mode & 2:
    return mt5.ORDER_FILLING_IOC
  return mt5.ORDER_FILLING_RETURN


def clamp_volume(symbol: str, requested_volume: float) -> float:
  """Clamps volume to symbol min/max and rounds to volume_step."""
  info = mt5.symbol_info(symbol)
  if info is None:
    return requested_volume

  step = info.volume_step if info.volume_step > 0 else 0.01
  vol = max(info.volume_min, min(info.volume_max, requested_volume))
  steps = round(vol / step)
  clamped = round(steps * step, 8)
  return max(info.volume_min, clamped)


def open_market_trade(
    symbol: str = "EURUSD",
    side: str = "BUY",
    volume: float = 0.01,
    magic: int = 234000,
):
  print("1. Calling mt5.initialize()...")
  init_ok = mt5.initialize(path=MT5_PATH) if MT5_PATH else mt5.initialize()
  if not init_ok:
    print(f"[ERROR] mt5.initialize() failed: {mt5.last_error()}")
    return None
  print("2. MT5 initialized.")

  try:
    term = mt5.terminal_info()
    if term and not term.trade_allowed:
      print(
          "[ERROR] Algo Trading is disabled on the MT5 terminal. Enable 'Algo"
          " Trading' in MT5 and retry."
      )
      return None

    if not mt5.symbol_select(symbol, True):
      print(f"[ERROR] Failed to select symbol {symbol}: {mt5.last_error()}")
      return None

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
      print(f"[ERROR] Failed to fetch tick for {symbol}: {mt5.last_error()}")
      return None

    side_upper = side.upper()
    if side_upper == "BUY":
      order_type = mt5.ORDER_TYPE_BUY
      price = tick.ask
    elif side_upper == "SELL":
      order_type = mt5.ORDER_TYPE_SELL
      price = tick.bid
    else:
      print(f"[ERROR] Invalid side '{side}'. Use 'BUY' or 'SELL'.")
      return None

    valid_volume = clamp_volume(symbol, volume)
    filling_mode = pick_filling_mode(symbol)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": valid_volume,
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": magic,
        "comment": f"DirectOpen_{side_upper}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    print("3. Running order_check...")
    chk = mt5.order_check(request)
    if chk is None:
      print(f"[ERROR] order_check failed: {mt5.last_error()}")
      return None
    if chk.retcode != 0:
      print(
          f"[REJECTED BY ORDER_CHECK] retcode={chk.retcode} |"
          f" comment={chk.comment}"
      )
      return None

    print("4. Sending order via order_send...")
    result = mt5.order_send(request)
    if result is None:
      print(f"[ERROR] order_send returned None: {mt5.last_error()}")
      return None

    print(
        f"order_send finished -> retcode={result.retcode} ({result.comment}) |"
        f" order={result.order} | deal={result.deal} | volume={result.volume} |"
        f" price={result.price}"
    )
    return result
  finally:
    mt5.shutdown()


if __name__ == "__main__":
  open_market_trade(symbol="EURUSD", side="BUY", volume=0.01, magic=234000)