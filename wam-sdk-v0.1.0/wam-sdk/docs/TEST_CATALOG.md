# Test catalog

Static case identifiers correspond to the public JSON/JUnit evidence.

## selftest

| Case | Criterion |
| --- | --- |
| SDK-001 | WAM conversion retains one-watoshi precision and rejects floats/invalid syntax |
| SDK-002 | Decimal context precision cannot round RPC amounts |
| SDK-003 | JSON request encoder emits exact numeric amounts and rejects floats |
| SDK-004 | Configuration rejects DNS names, remote hosts, URL credentials and path injection |
| SDK-005 | Auth/config/request representations do not expose secrets or payment data |
| SDK-006 | Cookie rotation is applied to the next request |
| SDK-007 | Ambient proxy variables are ignored |
| SDK-008 | All HTTP redirects are rejected without contacting their destination |
| SDK-009 | RPC error bodies never appear in exceptions or stdout/stderr |
| SDK-010 | Malformed, duplicate-key, nonfinite and mismatched-ID responses fail closed |
| SDK-011 | RPC responses are bounded by a configurable maximum size |
| SDK-012 | Mainnet mismatch blocks address allocation before any mutation |
| SDK-013 | Wrong genesis blocks operations despite matching chain name |
| SDK-014 | Read-only defaults prohibit address allocation and spending |
| SDK-015 | Send cap is enforced before transport and exact amounts reach the wire |
| SDK-016 | Ambiguous mutation response returns outcome_unknown and is never retried |
| SDK-017 | Wallet names are percent-encoded in the RPC route |
| SDK-018 | Inconsistent block/header telemetry and wallet scanning block readiness |
| SDK-019 | Receipt sums outputs exactly, deduplicates outpoints and respects confirmations |
| SDK-020 | Conflicting duplicate output evidence fails atomically |
| SDK-021 | Mempool eviction, abandoned transactions and coinbase do not count as payments |
| SDK-022 | A tip change during receipt scanning invalidates the snapshot |
| SDK-023 | Unowned addresses and cross-network payment requests are rejected |
| SDK-024 | Tracker latches review after a previously confirmed payment loses confirmations |
| SDK-025 | An outage preserves the last receipt while disabling fulfillment |
| SDK-026 | Freshness uses monotonic time and expires without a new poll |
| SDK-027 | Payment request serialization round-trips and rejects unknown fields |
| SDK-028 | Session pseudonyms cannot link the same value across independent sessions |
| SDK-029 | Concurrent reads use separate connections and unique request IDs |
| SDK-030 | Invalid or missing authentication is rejected without sending a request |
| SDK-031 | SDK-generated addresses use empty labels and Taproot by default |
| SDK-032 | Socket timeouts are safe read errors or ambiguous mutations without automatic retry |
| SDK-033 | Payment polling requests only the invoice address and review latch is read-only |

## regtest

| Case | Criterion |
| --- | --- |
| LIVE-001 | Read actual WAM chain identity and typed supply figures |
| LIVE-002 | Generate distinct real Taproot receive addresses without customer labels |
| LIVE-003 | Exact SDK send and receipt transitions through zero, one and two confirmations |
| LIVE-004 | Multiple real payments accumulate without duplicate accounting |
| LIVE-005 | Real chain invalidation revokes fulfillment and review remains latched after restoration |
| LIVE-006 | SDK fails closed when WAM v0.1.11 reports stale header height after reconsiderblock |
| LIVE-007 | Node restart rotates auth and failed polling disables fulfillment without erasing the receipt |
| LIVE-008 | Balance is an exact Amount from a real descriptor wallet |
| LIVE-009 | Read-only configuration refuses spend even with a funded real wallet |
| LIVE-010 | Node-status example executes and exports only minimal node metadata |
| LIVE-011 | Create/check examples work through private payment-request files |
| LIVE-012 | Send example submits once and refuses reuse of the same result path before resending |
| LIVE-013 | Self-contained checkout example completes against its own fresh daemon |
