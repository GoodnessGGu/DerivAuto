from app.deriv.client import DerivClient
from app.core.logging import log

class DerivTrader:
    def __init__(self, client: DerivClient):
        self.client = client

    async def execute_contract(self, **kwargs):
        """High-level flow: Proposal -> Buy."""
        try:
            # 1. Get Proposal
            proposal_resp = await self.proposal(**kwargs)
            
            if "error" in proposal_resp:
                return {"success": False, "error": proposal_resp["error"].get("message")}
            
            proposal_id = proposal_resp["proposal"]["id"]
            ask_price = float(proposal_resp["proposal"]["ask_price"])
            
            # 2. Buy
            buy_resp = await self.client.buy(proposal_id, ask_price)
            
            if "error" in buy_resp:
                return {"success": False, "error": buy_resp["error"].get("message")}
            
            buy_info = buy_resp["buy"]
            return {
                "success": True,
                "contract_id": buy_info["contract_id"],
                "buy_price": buy_info["buy_price"],
                "start_time": buy_info["start_time"]
            }

        except Exception as e:
            log.error(f"Execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def proposal(self, symbol: str, contract_type: str, amount: float, **kwargs):
        """Request a contract proposal with optional advanced parameters."""
        payload = {
            "proposal": 1,
            "symbol": symbol,
            "contract_type": contract_type,
            "amount": amount,
            "basis": "stake",
            "currency": kwargs.get("currency", "USD")
        }
        
        # Add basic duration if present
        if "duration" in kwargs and kwargs["duration"]:
            payload["duration"] = kwargs["duration"]
            payload["duration_unit"] = kwargs.get("duration_unit", "m")

        # Add Digits/Barriers
        if "barrier" in kwargs and kwargs["barrier"]:
            payload["barrier"] = str(kwargs["barrier"])
        if "barrier2" in kwargs and kwargs["barrier2"]:
            payload["barrier2"] = str(kwargs["barrier2"])
            
        # Add Multipliers
        if contract_type in ["MULTUP", "MULTDOWN"]:
            # Default to 100 for Forex/Gold, 10 for synthetics if not provided
            default_mult = 100 if "frx" in symbol or "XAU" in symbol.upper() else 10
            multiplier = kwargs.get("multiplier") or default_mult
            payload["multiplier"] = multiplier
            
            # Limit orders
            limit_order = {}
            for field in ["take_profit", "stop_loss"]:
                val = kwargs.get(field)
                if val is not None:
                    spot = kwargs.get("spot_price")
                    if spot is None:
                        # Auto-fetch spot price and cache it for the next field
                        tick_resp = await self.client.send_request({"ticks_history": symbol, "end": "latest", "count": 1, "adjust_start_time": 1})
                        if not tick_resp.get("error") and tick_resp.get("history") and tick_resp["history"].get("prices"):
                            spot = float(tick_resp["history"]["prices"][0])
                            kwargs["spot_price"] = spot  # cache to avoid re-fetching
                        else:
                            log.warning(f"Could not fetch spot price for {symbol}. Skipping conversion for {field}.")

                    if spot is not None:
                        if abs(val - spot) < abs(val):
                            # val is an absolute price level → convert to profit/loss dollar amount
                            price_diff = abs(val - spot)
                            calc_amount = round(float(amount) * float(multiplier) * (price_diff / spot), 2)
                            
                            # Deriv Multiplier Rules: 
                            # 1. Minimum limit order is $1.00
                            # 2. Stop loss cannot exceed the stake amount (e.g. $10.00 for $10.00 stake)
                            final_amount = max(calc_amount, 1.00)
                            if field == "stop_loss" and contract_type in ["MULTUP", "MULTDOWN"]:
                                final_amount = min(final_amount, float(amount) * 0.95)
                            
                            limit_order[field] = round(final_amount, 2)
                            log.info(f"[LimitOrder] {field}: price_level={val} spot={spot:.2f} diff={price_diff:.4f} -> ${limit_order[field]}")
                        else:
                            # val is already a dollar amount
                            final_amount = max(float(val), 1.00)
                            if field == "stop_loss" and contract_type in ["MULTUP", "MULTDOWN"]:
                                final_amount = min(final_amount, float(amount) * 0.95)
                            limit_order[field] = round(final_amount, 2)
                            log.info(f"[LimitOrder] {field}: raw_amount=${limit_order[field]}")
                    else:
                        # If spot could not be determined, assume val is already an amount
                        limit_order[field] = max(float(val), 1.00)

            if limit_order:
                log.info(f"[LimitOrder] Sending to Deriv: {limit_order}")
                payload["limit_order"] = limit_order

        # Prediction for digits
        if "prediction" in kwargs and kwargs["prediction"] is not None:
            payload["barrier"] = str(kwargs["prediction"])

        return await self.client.send_request(payload)

    async def check_contract_status(self, contract_id: int):
        """Fetch result for a contract."""
        resp = await self.client.send_request({"proposal_open_contract": 1, "contract_id": contract_id})
        return resp.get("proposal_open_contract")
