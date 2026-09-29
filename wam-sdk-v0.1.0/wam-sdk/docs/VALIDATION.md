# Validation and provenance — v0.1.0

Measured on 2026-09-29, Linux x86-64, CPython 3.12.14.

| Profile | Passed | Failed | Errors | Not run |
| --- | ---: | ---: | ---: | ---: |
| SDK self-tests | 33 | 0 | 0 | 0 |
| Real WAM regtest integration | 13 | 0 | 0 | 0 |
| Total | **46** | **0** | **0** | **0** |

Machine-readable evidence is in `reports/selftest/` and `reports/regtest/`.
The [case catalog](TEST_CATALOG.md) maps static IDs to criteria. No skipped or
expected-failure cases are counted as passing.

## What ran

Self-tests exercised exact amounts and wire encoding, malformed responses,
redirect rejection, environment proxy avoidance, credential rotation,
redacted errors, network/genesis mismatch, permissions and send caps,
ambiguous/timed-out sends without retries, output accounting, abandoned and
conflicted transactions, tip changes, freshness, the review latch, strict
request serialization, session pseudonyms and concurrent reads.

Live tests used the official WAM v0.1.11 Linux daemon with synthetic wallets.
They exercised chain/supply reads, fresh Taproot addresses, one-watoshi send
precision, zero/one/two confirmations, partial payments and overpayment,
chain invalidation and restoration, node restart and cookie rotation, exact
balance reads, read-only refusal, and all five example programs as child
processes. A second run of the send example with the same result path was
rejected before another payment.

The source suites import the development tree. The delivered wheel is also
built and installed in a separate virtual environment for an import/amount
check and a complete disposable regtest checkout. Wheel packaging does not
include test fixtures, examples, reports or daemon binaries.

The wheel import/one-watoshi check and its real checkout both passed. The
checkout moved from `confirming` to `paid`, with fulfillment eligibility true.
All 10 installed package files were byte-compared with `src/wam_sdk`.
Wheel SHA-256:
`ed548c905235d33cd909225ffefcd27d26e657b6fd3299b98727e62f1bf3b25f`.

Public JSON and JUnit files passed `scripts/check_report.py`. Reports use static
IDs and fixed categories, excluding raw RPC payloads and fixture values.

## WAM provenance

Official repository:
<https://github.com/wamcoin-core-dev/wam-coin>

- Release/tag: `v0.1.11`
- Source commit: `8a3f4fe4f1d804c378f795d4cc281ec5125f75f3`
- Genesis constants: `src/wam/chainparams.cpp` at that commit
- WAM supply RPC: `src/wam/rpc/wam_rpc.cpp` at that commit
- Observed upstream `main` when inspecting venue integration work:
  `5b9cb8f6a79c04e0ffb6244d045a4a51a896ea59`
- Release archive: `wam-coin-v0.1.11-x86_64-linux-gnu.tar.gz`
- Archive SHA-256:
  `bd010ed615ab8063d5c12aa61236311ece7e9d19896d9541dacba1888dd9987a`
- Executed `wamd` SHA-256:
  `625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4`

The checksum pins the observed release bytes; it does not independently prove
the publisher's identity or a reproducible daemon build. The binary is not
redistributed in this SDK archive. The fetch helper verifies both digests.

## Known Core behavior preserved in the tests

On the pinned daemon, `reconsiderblock` restores the active blocks but can leave
the reported header height at the previously invalidated height until a fresh
block is mined. `LIVE-006` verifies that SDK readiness becomes false and address
allocation is rejected during this mismatch; it then mines a fresh regtest
block to restore consistent telemetry.

This passing SDK test verifies fail-closed behavior. It does **not** mean the
underlying Core issue has been fixed. The earlier WAM/Pay/Watchtower integration
findings remain separate; this package changes none of their source code.

## Scope not established by these results

- No mainnet/testnet transaction, real customer wallet, production deployment,
  independent audit or load/performance benchmark was performed.
- Cross-platform GitHub Actions jobs are supplied but have not been executed.
- Local test node settings restrict activity to loopback; an additional OS
  network namespace could not be created in this execution environment.
  Do not interpret the local result as an OS egress isolation attestation.
- A normal cleanup path was exercised. Crash/power-loss cleanup, durable send
  idempotency and exactly-once order fulfillment are application responsibilities.
- CI dependency downloads and main/test readiness heuristics are not evidence
  that a node has the globally best chain or that the software is anonymous.

## Reproduce

Install the included wheel using README instructions. Fetch the pinned daemon
or supply an executable with its verified digest. Run both commands in README
using new report directories; a pre-existing directory is rejected to prevent
accidental evidence overwrite. `scripts/build_bundle.py --output NEW.zip`
packages only the approved source, wheel, docs and validated report files.
