# API and integration contract

Import the public API from `wam_sdk`. Modules under `devtools`, `tests` and
`examples` are source-bundle utilities, not installed SDK APIs.

## Configuration

| Setting | Default / behavior |
| --- | --- |
| `url` | Required `http://127.0.0.1:PORT`; optional trailing slash |
| `network` | Required `Network.MAIN`, `.TEST` or `.REGTEST` |
| `auth` | Required `CookieAuth(Path(...))` or `BasicAuth(user, password)` |
| `timeout` | 10 seconds per blocking socket operation; maximum 120 |
| `max_response_bytes` | 4 MiB, configurable from 256 bytes to 16 MiB |
| `max_tip_age_seconds` | 3600; applies to main/test readiness |
| `allow_new_addresses` | `False`; must enable to allocate payment addresses |
| `send_limit` | `None`; otherwise positive `Amount`, maximum per send before fees |

`Config.from_env()` requires `WAM_RPC_URL` and `WAM_NETWORK`. It uses
`WAM_COOKIE_FILE` when set, otherwise requires both `WAM_RPC_USER` and
`WAM_RPC_PASSWORD`. Mutation capabilities must still be passed as keyword
arguments; environment variables do not enable them.

Loopback is a deliberate v0.1.0 scope boundary. IPv6, remote HTTP/HTTPS, DNS
hostnames, Unix sockets, SOCKS and automatic tunneling are not supported.

## Money

`Amount.from_wam("1.00000001")` represents 100000001 watoshis.
`Amount(1)` represents one watoshi. `.units` returns the integer and `.text`
returns eight decimal places. `str(amount)` is an explicit value disclosure;
`repr(amount)` hides the value.

Amounts are nonnegative and bounded by 22 million WAM. Public decimal strings
reject whitespace, scientific notation, signs, leading zeroes, non-finite
values and more than eight fractional places. `float` and `bool` are rejected.
RPC decimals are decoded without float conversion or Decimal-context rounding.

## Operations

| Method | Result / behavior |
| --- | --- |
| `client.status()` | `NodeStatus`: network, blocks, headers, IBD, tip, ready |
| `client.supply()` | Height plus `Amount` fields: circulating, max_supply, premine, block_subsidy |
| `client.wallet(name)` | Wallet handle; percent-encodes the route |
| `wallet.balance(min_confirmations=1)` | Exact amount; node and wallet must be ready |
| `wallet.new_address(address_type="bech32m")` | Fresh owned/watch-only receive address; also supports `bech32` |
| `wallet.create_request(amount, confirmations=6)` | `PaymentRequest` with random ID and fresh address |
| `wallet.observe(request, known_txids=())` | `PaymentReceipt` at a consistent observed tip |
| `wallet.send(address, amount)` | Transaction ID, explicit send capability required |

The SDK does not create/load/unlock wallets, export keys, request a seed, set
node policy or expose a public arbitrary-RPC escape hatch. Signing and fee
selection are delegated to the daemon's wallet. A send cap covers the payment
amount, not fees or aggregate/concurrent spending. There is no automatic RBF,
refund or resend API in this release.

`status()` checks chain identity and genesis, then requires no IBD and equal
block/header heights for `ready=True`. Main/test also require a positive peer
count and a tip no older than the configured maximum (or more than two hours
in the future). Wallet readiness requires no scan in progress and its last
processed hash to match the observed node tip.

These are local observations, not proof that the node sees the global best
chain. The daemon is trusted. Separate RPC calls cannot provide a transactional
snapshot; tip checks reject detected changes during balance/payment reads.

## Payment integration contract

`PaymentRequest.to_dict()` and `.from_dict()` serialize a versioned, strict
schema. The dictionary contains sensitive business data. Persist it before
giving the address to a customer; attach customer/order metadata only in your
private application database. Allocate one request per order and reuse that
request on application retries rather than allocating another address.

`observe()` queries the request's address, merges any supplied known txids and
re-reads each transaction. It deduplicates `(txid, vout)`, counts incoming outputs
only, ignores coinbase, abandoned and conflicted transactions, and requires
zero-confirmation transactions to remain in the mempool. It checks the wallet
and chain tip again before returning. It rejects more than 2000 candidate
txids and inconsistent output data instead of returning partial accounting.

Receipt states are `pending`, `partial`, `confirming`, or `paid`. `.received`
includes eligible unconfirmed receipts; `.confirmed` includes outputs meeting
the request's threshold. `.paid` is true when confirmed total meets or exceeds
the requested amount. Overpayments are counted; refund policy belongs to the
application. Sending funds onward does not erase the original payment receipt.

`PaymentTracker(wallet, request, freshness_seconds=30)` retains observed txids
within the process. `refresh()` disables eligibility before polling and
retains the previous receipt if polling fails. Eligibility requires a healthy
poll, a monotonic age within the freshness window, a paid receipt and no review
latch. A paid-to-unpaid transition sets the read-only `needs_review` flag;
restoring confirmations does not clear it automatically.

For a long-running merchant service:

1. Persist requests, previously known txids, paid/review history and fulfillment
   state in an access-controlled database. Tracker state is in memory only;
   restarting it must not clear a durable review decision.
2. Serialize polling and decisions per request. `PaymentTracker` is not thread
   safe; concurrent calls require an application lock. Client reads use separate
   connections, but a shared client does not implement spending serialization.
3. Claim fulfillment atomically by unique request ID and use an idempotent job
   or transactional outbox for the business action. A paid receipt is not a
   database lock and cannot make an external action exactly once.
4. Fail closed on RPC outages, readiness errors, inconsistent snapshots and
   review state. Continue reconciliation after delivery to detect later reorgs.

An application can use `wallet.observe(request, known_txids=...)` directly with
its durable state machine. This SDK supplies payment observations, not a hosted
checkout, database schema, invoice expiry engine or a replacement for WAM Pay.

## Errors and uncertain sends

Catch `WamError`. Its `.code` is an `ErrorCode`, `.rpc_code` may contain the
numeric upstream RPC code, and `.outcome_unknown` signals an uncertain mutation.
`str(error)` contains a fixed code, not upstream error text.

| Error category | Application handling |
| --- | --- |
| `invalid_configuration`, `authentication_failed` | Correct endpoint/auth setup |
| `invalid_amount`, `invalid_input`, `operation_not_enabled` | Correct or authorize the requested operation |
| `network_mismatch` | Stop; investigate node identity |
| `node_or_wallet_not_ready`, `inconsistent_snapshot` | Withhold fulfillment; poll reads again later |
| `transport_failed`, `request_timeout` | Mark reads unhealthy; apply bounded application backoff |
| `invalid_rpc_response`, `response_too_large` | Withhold decisions; inspect trusted node/limits privately |
| `rpc_rejected` | Interpret numeric RPC code without publishing raw node logs |
| `mutation_outcome_unknown` | Reconcile wallet state before deciding on another mutation |

No operation is automatically retried. A send whose response is lost, redirected,
malformed, oversized or timed out may already have been submitted. There is no
durable send idempotency key. Never blindly retry that send. The regtest send
example reserves a result file before sending to prevent accidental reruns with
the same path; it is not a transactional journal and a power loss can leave a
partial file. Never delete or rename an unresolved sentinel to force a retry.

## Optional labels

`SessionLabels().label(value)` yields a pseudonym using a fresh random HMAC key.
Labels repeat within that instance but differ across instances. They are not
needed by the SDK and are never written automatically. Do not use them as a
durable invoice identifier or a claim of anonymous telemetry.
