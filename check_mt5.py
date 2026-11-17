import MetaTrader5 as mt5
import time
import pandas as pd

def verify_connection():
    print("Initializing MetaTrader 5 connection...")
    if not mt5.initialize():
        print(f"ERROR: mt5.initialize() failed, error code = {mt5.last_error()}")
        print("Please ensure MT5 desktop is open and 'Allow algorithmic trading' is checked in Tools > Options > Expert Advisors.")
        return False

    print("SUCCESS: Connected to MT5 terminal!")
    print("Terminal version:", mt5.version())
    
    account = mt5.account_info()
    if account is not None:
        acc_dict = account._asdict()
        print(f"Account Login: {acc_dict.get('login')}, Server: {acc_dict.get('server')}, Balance: {acc_dict.get('balance')}")
    else:
        print("WARNING: Could not retrieve account info.")

    symbol = "EURUSD"
    if not mt5.symbol_select(symbol, True):
        print(f"ERROR: Failed to select symbol {symbol}, error code = {mt5.last_error()}")
        mt5.shutdown()
        return False

    print(f"SUCCESS: Symbol {symbol} selected in Market Watch.")
    print("Testing live tick stream for 5 seconds...")
    
    start_time = time.time()
    tick_count = 0
    while time.time() - start_time < 5:
        tick = mt5.symbol_info_tick(symbol)
        if tick is not None:
            tick_count += 1
            print(f"[{tick_count}] Time: {pd.to_datetime(tick.time, unit='s')} | Bid: {tick.bid} | Ask: {tick.ask}")
        time.sleep(1)

    mt5.shutdown()
    if tick_count > 0:
        print("\n100% VERIFIED: MT5 is connected and successfully transmitting ticks!")
        return True
    else:
        print("\nWARNING: Connected, but no ticks received yet (market might be closed or symbol inactive).")
        return False

if __name__ == "__main__":
    verify_connection()
