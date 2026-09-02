"""Create a Polymarket trading key and print the address to fund.

**Run this on your own machine, not on the server and not in a chat
session.** It prints a private key and a mnemonic. Anything printed inside
an AI session is written to that session's transcript, which is the wrong
home for a key that controls money.

    pip install py-clob-client eth-account
    python scripts/setup_wallet.py

It prints four things:

    EOA address    the keypair that signs orders. Holds nothing.
    PRIVATE KEY    goes in .env on the server. Never anywhere else.
    MNEMONIC       write on paper. The only recovery if the server dies.
    PROXY address  **this is what you fund.**

The proxy is a contract address derived from the EOA. Sending USDC to the
EOA instead is the single most common way to lose it, so the script prints
them far apart and labels which is which.
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from eth_account import Account
    except ImportError:
        sys.exit("pip install py-clob-client eth-account")

    Account.enable_unaudited_hdwallet_features()
    acct, mnemonic = Account.create_with_mnemonic()

    print("\n" + "=" * 68)
    print("  WRITE THE MNEMONIC ON PAPER BEFORE CLOSING THIS WINDOW")
    print("=" * 68)
    print(f"\n  MNEMONIC     {mnemonic}\n")
    print(f"  EOA address  {acct.address}")
    print(f"               (signs orders, holds nothing, DO NOT FUND THIS)")
    print(f"\n  PRIVATE KEY  {acct.key.hex()}")
    print( "               -> POLY_PRIVATE_KEY in /opt/polybuyer/.env, chmod 600")

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.constants import POLYGON
    except ImportError:
        print("\n  (install py-clob-client to derive the proxy address)")
        return

    c = ClobClient("https://clob.polymarket.com", key=acct.key.hex(),
                   chain_id=POLYGON, signature_type=1)
    print("\n" + "-" * 68)
    print(f"  PROXY        {c.get_address()}")
    print( "               *** FUND THIS ONE. Send USDC on Polygon. ***")
    print("-" * 68)
    print("\n  Before sending real money:")
    print("   1. Open the proxy address on polygonscan.com and confirm it exists.")
    print("   2. Send $5. Confirm it shows in your Polymarket balance.")
    print("   3. Withdraw that $5 back out. Prove the exit works FIRST.")
    print("   4. Only then fund properly.\n")


if __name__ == "__main__":
    main()
