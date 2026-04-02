import asyncio
import json
import ssl
import websockets
from typing import Dict, Any, Optional, Callable, List
from app.core.logging import log
from app.config import settings
import time

class DerivClient:
    def __init__(self, app_id: int, token: str):
        self.app_id = app_id
        self.token = token
        self.uri = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"
        self.ws: Optional[Any] = None
        self.is_authorized = False
        self.subscriptions: Dict[str, str] = {}  # symbol -> req_id or subscription_id
        self._callback_handlers: Dict[str, Callable] = {}
        self._request_futures: Dict[str, asyncio.Future] = {}
        self._reconnect_delay = 1
        self._running = False
        self._req_id_counter = 0 # Unique request counter
        self.connected_event = asyncio.Event()

    async def connect(self):
        """Establish WebSocket connection and authorize."""
        while True:
            try:
                log.info(f"Connecting to Deriv WebSocket: {self.uri}")
                ssl_context = ssl.create_default_context()
                self.ws = await websockets.connect(self.uri, ssl=ssl_context)
                self._running = True
                self.connected_event.set() # Allow send_request to proceed for authorization
                
                # Start listener background task
                asyncio.create_task(self._listen())
                
                authorized = await self.authorize()
                if authorized:
                    log.info("Deriv Authorization Successful")
                    self.is_authorized = True
                    self._reconnect_delay = 1
                    # Resubscribe to previous symbols if any
                    await self._resubscribe()
                    return True
                else:
                    log.error("Deriv Authorization Failed")
                    self.connected_event.clear()
                    await self.ws.close()
            except Exception as e:
                log.error(f"Connection error: {e}. Retrying in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    async def authorize(self, token: Optional[str] = None) -> bool:
        """Send authorize request."""
        target_token = token or self.token
        log.info(f"Authorizing client with token: {target_token[:4]}...{target_token[-4:]}")
        response = await self.send_request({"authorize": target_token})
        
        if "authorize" in response:
            self.token = target_token
            self.is_authorized = True
            return True
        return False

    async def switch_account(self, new_token: str):
        """Switches the active account by re-authorizing with a new token."""
        if not new_token:
            log.error("Switch failed: No token provided.")
            return False
            
        log.info("Switching Deriv account...")
        success = await self.authorize(new_token)
        if success:
            log.info("Account switch successful. Resubscribing to market data...")
            await self._resubscribe()
            return True
        else:
            log.error("Account switch failed: Authorization rejected.")
            return False

    async def _listen(self):
        """Listen for incoming messages."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                # Handle responses for pending futures
                req_id = str(data.get("req_id")) if data.get("req_id") else None
                if req_id and req_id in self._request_futures:
                    future = self._request_futures.pop(req_id)
                    if not future.done():
                        future.set_result(data)
                
                # Handle subscription updates (e.g., ticks)
                msg_type = data.get("msg_type")
                if msg_type in self._callback_handlers:
                    await self._callback_handlers[msg_type](data)
                
                # Handle errors
                if "error" in data:
                    log.error(f"API Error: {data['error'].get('message')}")

        except websockets.ConnectionClosed:
            log.warning("WebSocket connection closed")
        except Exception as e:
            log.error(f"Listener error: {e}")
        finally:
            self.is_authorized = False
            self.connected_event.clear()
            
            # If the client was supposed to be running, trigger a reconnect
            if self._running:
                log.info("WebSocket listener exited. Triggering reconnection...")
                self._running = False # Reset state
                asyncio.create_task(self.connect())
            else:
                self._running = False

    async def send_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request and wait for response using req_id. Waits for connection if down."""
        # Safety wait: If connection is down, pause here instead of crashing
        if not self.connected_event.is_set():
            log.warning(f"Connection down. Waiting to send {payload.get('msg_type', 'request')}...")
            try:
                await asyncio.wait_for(self.connected_event.wait(), timeout=20.0)
            except asyncio.TimeoutError:
                raise Exception("Request failed: WebSocket connection could not be established in time.")

        if not self.ws or self.ws.state.name != "OPEN":
            self.connected_event.clear()
            raise Exception("WebSocket not connected")
        
        self._req_id_counter += 1
        req_id = f"{int(time.time())}_{self._req_id_counter}"
        payload["req_id"] = req_id
        
        future = asyncio.get_event_loop().create_future()
        self._request_futures[req_id] = future
        
        await self.ws.send(json.dumps(payload))
        
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._request_futures.pop(req_id, None)
            raise Exception(f"Request timeout: {payload.get('msg_type', 'unknown')}")

    def register_handler(self, msg_type: str, handler: Callable):
        """Register a callback for a specific message type."""
        self._callback_handlers[msg_type] = handler

    async def subscribe_ticks(self, symbol: str):
        """Subscribe to real-time ticks for a symbol."""
        log.info(f"Subscribing to ticks for {symbol}")
        response = await self.send_request({"ticks": symbol, "subscribe": 1})
        if "tick" in response:
            self.subscriptions[symbol] = response["tick"].get("id")
            return response
        return None

    async def _resubscribe(self):
        """Resubscribe to all symbols in the current subscription list."""
        symbols = list(self.subscriptions.keys())
        self.subscriptions.clear()
        for symbol in symbols:
            await self.subscribe_ticks(symbol)

    async def ping(self):
        """Performs a diagnostic heartbeat by requesting server time."""
        if not self.ws or self.ws.state.name != "OPEN":
            self.connected_event.clear()
            return

        try:
            # A functional request (time) is more reliable than a simple ping
            # because it verifies the API is actually processing messages.
            await self.send_request({"time": 1})
            log.debug("Heartbeat: API Responsive.")
        except Exception as e:
            log.warning(f"Heartbeat: API Unresponsive ({e}). Triggering Reconnect...")
            self.connected_event.clear()
            if self.ws:
                await self.ws.close()
            # The _listen task or main loop will trigger connect()

    async def buy(self, proposal_id: str, price: float):
        """Buy a contract based on a proposal."""
        return await self.send_request({
            "buy": proposal_id,
            "price": price
        })

    async def proposal(self, symbol: str, contract_type: str, amount: float, duration: int, unit: str):
        """Request a contract proposal."""
        return await self.send_request({
            "proposal": 1,
            "symbol": symbol,
            "contract_type": contract_type,
            "amount": amount,
            "duration": duration,
            "duration_unit": unit,
            "currency": "USD"
        })
