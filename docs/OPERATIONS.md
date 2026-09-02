# Running the desk: account, funding, hosting

## 1. The Polymarket account

Polymarket's architecture is two addresses, and the distinction matters for
funding:

- **Your EOA** — an ordinary Ethereum keypair. Signs orders. Holds no funds.
- **Your proxy wallet** — a contract address deterministically derived from
  the EOA. **This is what holds USDC and positions**, and it is the address
  you fund.

Trading through the API needs L1 → L2 credentials: you sign a message with
the EOA private key once, and Polymarket returns an API key, secret and
passphrase. Those are what the client uses from then on.

### Generating the key — do this yourself, not here

**I have deliberately not generated a key for you.** Anything created in
this session passes through my context and the session transcript, which is
the wrong place for a key that will control real money. Run this on your
own machine, offline if you like:

```bash
pip install py-clob-client eth-account
python - <<'PY'
from eth_account import Account
Account.enable_unaudited_hdwallet_features()
acct, mnemonic = Account.create_with_mnemonic()
print("EOA address :", acct.address)
print("PRIVATE KEY :", acct.key.hex())
print("MNEMONIC    :", mnemonic)
PY
```

Write the mnemonic down on paper. Put the private key in `.env` on the
server only, `chmod 600`, never in the repo.

### Deriving the proxy address and API credentials

```python
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

c = ClobClient("https://clob.polymarket.com", key=PRIVATE_KEY,
               chain_id=POLYGON, signature_type=1)   # 1 = email/magic proxy
print("proxy (fund THIS):", c.get_address())
creds = c.create_or_derive_api_creds()      # L1 signature -> L2 credentials
print(creds.api_key, creds.api_secret, creds.api_passphrase)
```

`signature_type` decides which proxy is derived, so **confirm the printed
address matches what Polymarket shows for your account before sending
anything**.

### Funding from Coinbase

Coinbase can withdraw USDC directly on the **Polygon** network, which
avoids bridging:

1. Coinbase → Send USDC → choose **Polygon** as the network.
2. Paste the **proxy** address, not the EOA.
3. **Send $5 first.** Confirm it appears in the Polymarket balance before
   sending the rest. A wrong network or the EOA instead of the proxy is how
   people lose the lot, and neither is recoverable by me or by support.

Polymarket uses native USDC on Polygon. If Coinbase offers you USDC.e or a
bridged variant, don't — send native.

### Two things that are yours to confirm

Eligibility and terms of service are between you and Polymarket; I can't
advise on whether API access is permitted for you, and you should read
their terms rather than take my word. Separately, funds in a proxy wallet
are only as safe as the key on the server — size the balance to what the
strategy needs, not to what is convenient.

---

## 2. Where the autofire scripts live

```
polybuyer/newsdesk/
    engine.py     the long-running process: stream -> gate -> guards -> order
    store.py      newsdesk.db, the armed markets and the fire log
    rules.py      builds the stream rule set from the DB
    gate.py       the LLM questions
    guards.py     the don't-chase checks
```

`engine.py` is the only thing that runs continuously. Everything else in
the repo is research and runs on demand.

### Why it must be one process

X allows **one filtered-stream connection per app**. Two processes means
one silently gets disconnected. So the engine is a single long-lived
process holding that connection, and the market list is reloaded from the
DB rather than from a restart.

The stream is push, not poll — X delivers the post, the engine does not go
looking. That is what makes 2-second latency achievable and why there is no
polling loop anywhere in the design.

### The loop

1. Load armed markets, build rules, `PUT` them to X (replacing the old set).
2. Hold the connection open. On each delivered post, the rule **tag** says
   which market and which tier matched — no re-matching.
3. Tier 2 posts below `min_followers` are dropped before the gate. The post
   is already paid for; this only saves the LLM call.
4. Gate the post. Compare direction in code, never in the prompt.
5. Check the guards against a fresh price. Breach → record blocked, disarm.
6. Fire at `limit_price(mid, direction, aggression)`, size by tier.
7. Disarm the market and log the fire either way.

### Keeping it alive

X **requires** exponential backoff on reconnect and will rate-limit an
aggressive reconnector. The engine must:

- reconnect with backoff (start 5s, cap ~320s), jittered
- treat a 20-second silence as a dead connection — X sends keepalive
  newlines, so silence is not idleness
- re-`PUT` rules on start, since the rule set is server-side state that
  drifts when the DB changes

systemd handles the process; the engine handles the connection:

```ini
# /etc/systemd/system/newsdesk.service
[Unit]
Description=Polybuyer news desk
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=newsdesk
WorkingDirectory=/opt/polybuyer
EnvironmentFile=/opt/polybuyer/.env
ExecStart=/opt/polybuyer/.venv/bin/python -m polybuyer.newsdesk.engine
Restart=always
RestartSec=10
# A crash loop must not become an X rate-limit ban.
StartLimitIntervalSec=300
StartLimitBurst=5
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/polybuyer/data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now newsdesk
journalctl -u newsdesk -f
```

---

## 3. Hosting, in Ireland

**AWS `eu-west-1` is Dublin** and is the straightforward answer: a
`t4g.small` is more than enough (the engine is IO-bound on one socket), at
roughly $12–15/month. **Azure `North Europe` is also Dublin** if you prefer
it.

Worth knowing: Hetzner and DigitalOcean have **no Irish region** — Hetzner
is Germany/Finland, so "cheap European VPS" advice will land you outside
Ireland. Blacknight is an Irish provider if you want a domestic company
rather than a US one with an Irish region.

Latency to X and to Polymarket's CLOB from Dublin is tens of milliseconds,
which is irrelevant here: the earlier out-of-sample work found 2-second and
45-second entries returned identically, with the cliff between 45s and
120s. Region is a jurisdiction decision, not a speed one.

### Minimum setup

```bash
sudo adduser --system --group newsdesk
sudo mkdir -p /opt/polybuyer/data && sudo chown -R newsdesk: /opt/polybuyer
git clone <repo> /opt/polybuyer && cd /opt/polybuyer
python3 -m venv .venv && .venv/bin/pip install py-clob-client
sudo install -m 600 -o newsdesk .env /opt/polybuyer/.env
```

`.env` needs `X_BEARER_TOKEN`, `OPENAI_API_KEY`, `POLY_PRIVATE_KEY`,
`NEWSDESK_DB=/opt/polybuyer/data/newsdesk.db`, and `NEWSDESK_PAPER=1`.

**Leave `NEWSDESK_PAPER=1` until the fire log looks right.** In paper mode
the engine does everything except send the order, and `fires` records what
it would have done — which is the only cheap way to find out that a rule
matches nothing, or everything.
