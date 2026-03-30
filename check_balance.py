import asyncio
import os
from dotenv import load_dotenv
from app.deriv.client import DerivClient
from app.config import settings

async def check_balance():
    # Load environment variables
    load_dotenv()
    
    token = os.getenv("DERIV_TOKEN")
    if not token or token == "your_real_deriv_token_here":
        print("Error: Please set a valid DERIV_TOKEN in the .env file.")
        return

    print(f"Connecting to Deriv with Token: {token[:5]}...")
    
    # Initialize client
    client = DerivClient(app_id=settings.DERIV_APP_ID, token=token)
    
    # Connect and Authorize
    success = await client.connect()
    
    if success:
        # The authorize call response is handled in client._listen and stored in futures
        # But we can also just call it again or look at the response from the first call
        # Actually, let's just request the account list directly if authorized
        auth_res = await client.send_request({"authorize": token})
        
        if "authorize" in auth_res:
            auth_data = auth_res["authorize"]
            accounts = auth_data.get("account_list", [])
            
            print("\n--- Linked Accounts & Balances ---")
            for acc in accounts:
                acc_type = "DEMO" if acc.get("is_virtual") else "REAL"
                loginid = acc.get("loginid")
                currency = acc.get("currency")
                
                # Check for balance in the account list entry or use the current authorized balance
                balance = acc.get("balance")
                if balance is None and loginid == auth_data.get("loginid"):
                    balance = auth_data.get("balance")
                
                balance_str = f"{balance}" if balance is not None else "N/A"
                print(f"[{acc_type}] ID: {loginid} | Balance: {balance_str} {currency}")
            print("----------------------------------\n")
        else:
            print("Error: Could not retrieve account list.")
    else:
        print("Error: Authentication failed.")

    # Cleanup
    if client.ws:
        await client.ws.close()

if __name__ == "__main__":
    asyncio.run(check_balance())
