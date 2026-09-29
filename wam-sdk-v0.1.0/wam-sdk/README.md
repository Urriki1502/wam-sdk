# WAM SDK for Python

An independent SDK for applications using a local WAM node: exact amounts,
typed node/wallet operations, fresh payment addresses and confirmation tracking.
Version **0.1.0**, Python **3.11+**, no third-party runtime dependencies.

This is an initial developer release, tested against **WAM Core v0.1.11 on
regtest**. It is not an official WAM project release or a production security audit.

[Hướng dẫn tiếng Việt](docs/QUICKSTART_VI.md) · [API](docs/API.md) ·
[Privacy](docs/PRIVACY.md) · [Validation](docs/VALIDATION.md)

## Install the included wheel

From the extracted project directory:

```sh
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# PowerShell alternative: .venv\Scripts\Activate.ps1
python -m pip install --no-index --no-deps dist/wam_sdk-0.1.0-py3-none-any.whl
```

The wheel is included in this source bundle. No PyPI publication is implied.
For source development, use `python -m pip install -e .`; that requires the
build dependencies declared in `pyproject.toml`.

## Read a local node

Configure a loopback RPC endpoint, its network and an explicit cookie path.
Use your node's actual port and path; the values below are placeholders.

```python
from pathlib import Path
from wam_sdk import Config, CookieAuth, Network, WamClient

client = WamClient(Config(
    url="http://127.0.0.1:18443",
    network=Network.REGTEST,
    auth=CookieAuth(Path("/absolute/private/datadir/regtest/.cookie")),
))
status = client.status()
print(status.network.value, status.blocks, status.ready)
```

Each operation checks the expected chain and pinned genesis. Wallet operations
also require a synchronized node and wallet. Main/test readiness additionally
requires peers and a recent tip. A fresh regtest chain must be bootstrapped before
using the wallet API; the disposable checkout example does this automatically.

## Create and observe a payment

```python
from dataclasses import replace
from wam_sdk import Amount, PaymentTracker, WamClient

merchant = WamClient(replace(client.config, allow_new_addresses=True)).wallet("merchant")
request = merchant.create_request(Amount.from_wam("1.25000001"), confirmations=6)
# Persist request.to_dict() in private application storage before presenting it.
# Present request.address and request.amount.text to this customer only.

tracker = PaymentTracker(merchant, request, freshness_seconds=30)
receipt = tracker.refresh()
if tracker.eligible_for_fulfillment:
    pass  # Atomically claim this request ID in your durable order system first.
```

`Amount` uses integer watoshis (1 WAM = 100,000,000 watoshis), never binary floats.
Requests use a new Taproot address and an empty wallet label. Receipts count
confirmed incoming outputs, including outputs already spent by the merchant;
they do not use the current UTXO balance as an invoice ledger.

`PaymentTracker` disables fulfillment after failed or stale polling. If a paid
payment becomes unpaid, it latches `needs_review`. It is an **in-memory** helper,
not a durable invoice service or an exactly-once fulfillment engine. See the
[integration contract](docs/API.md#payment-integration-contract) before using it
in a service.

## Five runnable examples

| File | Purpose |
| --- | --- |
| `examples/read_node.py` | Read minimal node status |
| `examples/create_payment_request.py` | Allocate a fresh address; save a private request |
| `examples/check_payment.py` | Observe a saved request at the current tip |
| `examples/send_regtest.py` | Send with an explicit cap, restricted to regtest |
| `examples/regtest_checkout.py` | Start a disposable daemon; pay and confirm a checkout |

The first four use `WAM_RPC_URL`, `WAM_NETWORK`, `WAM_COOKIE_FILE` and, for wallet
operations, `WAM_WALLET`. Explicit `WAM_RPC_USER` and `WAM_RPC_PASSWORD` are an
alternative to cookie authentication. Cookie auth is preferred; it is reread
for each call so node restarts can rotate credentials.

Run the complete local demo after installing the wheel:

```sh
python scripts/fetch_release.py
python examples/regtest_checkout.py --wamd .tools/wamd --sha256 625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4
```

The fetch helper downloads the pinned Linux x86-64 release and verifies both
archive and executable SHA-256. On Ubuntu 22.04 the daemon needs
`libevent-2.1-7` and `libevent-pthreads-2.1-7`. The demo creates its own regtest
wallets and directories, then removes them; it does not use a personal wallet.

## Privacy and spending defaults

- Direct IPv4 loopback RPC only; no DNS, redirects, environment proxies,
  automatic retries, telemetry or SDK logging.
- Fixed error codes instead of raw upstream error messages. Sensitive model
  representations hide values; explicit serialization is private data.
- Read-only by default. Address allocation and spending require separate,
  explicit configuration. `send_limit` limits each payment amount; fees are
  additional and it is not an aggregate budget.
- An uncertain mutation result raises `mutation_outcome_unknown`. Reconcile
  with the wallet before deciding whether another send is appropriate.
- Optional session pseudonyms use a fresh HMAC key per instance; no stable
  address hashes across sessions.

These measures reduce application data exposure. They do not make WAM chain
transactions anonymous or confidential. The host, daemon and wallet are trusted.

## Run tests

Use a new report directory for each run:

```sh
python scripts/run_tests.py selftest --report-dir reports/local-selftest
python scripts/run_tests.py regtest --wamd .tools/wamd --sha256 625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4 --report-dir reports/local-regtest
python scripts/check_report.py reports/local-regtest
```

Reports contain static case IDs, verdicts, error categories and the public
binary digest. Raw RPC data, transaction IDs, wallet paths and credentials are
excluded. The source archive includes the measured reports and the test catalog.

The upstream [`wam-coin/integration`](https://github.com/wamcoin-core-dev/wam-coin/tree/main/integration)
directory contains venue integration work. This SDK provides reusable application
APIs and examples alongside that work; it does not replace Core's functional
tests, WAM Pay or Watchtower. No changes to those repositories are bundled here.

License: MIT. See [LICENSE](LICENSE).
