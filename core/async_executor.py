import asyncio
import logging
import MetaTrader5 as mt5

logger = logging.getLogger("QuantEngine")

class AsyncOrderDispatcher:
    def __init__(self, max_concurrent=10):
        self.queue = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.is_running = False

    async def start_worker(self):
        self.is_running = True
        while self.is_running:
            request = await self.queue.get()
            try:
                await self.execute_order(request)
            except Exception as e:
                logger.error(f"Async order execution failed: {e}")
            finally:
                self.queue.task_done()

    async def execute_order(self, request):
        # Non-blocking wrapper for MetaTrader 5 order dispatch
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, mt5.order_send, request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.warning(f"Order failed with retcode: {result.retcode}")
        else:
            logger.info(f"Successfully filled order batch: {result.order}")

    async def enqueue_order(self, request):
        if self.queue.qsize() < self.max_concurrent * 5:
            await self.queue.put(request)
        else:
            logger.warning("Order queue saturated; dropping stale slice to prevent slippage.")