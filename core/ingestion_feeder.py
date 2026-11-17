import MetaTrader5 as mt5
import pandas as pd
from utils.logger import logger

def initialize_mt5(symbol="EURUSD"):
    if not mt5.initialize():
        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
        return False
    
    if not mt5.symbol_select(symbol, True):
        logger.error(f"Failed to select symbol {symbol}: {mt5.last_error()}")
        return False
        
    logger.info(f"Connected to MT5. Version: {mt5.version()}, Symbol: {symbol}")
    return True

def get_latest_tick(symbol="EURUSD"):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.warning(f"Failed to get tick for {symbol}")
        return None
    return {
        "time": tick.time,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "volume": getattr(tick, "volume", 1.0)
    }