# Privacy design and limits

The goal is to minimize accidental exposure through integration code and test
artifacts. This is an operational privacy design, not chain-level privacy.

## Data flow

Applications call a literal loopback RPC endpoint. The SDK talks directly to
the configured node over HTTP and does not consult proxy variables, resolve
hostnames, follow redirects, send analytics or write logs. It never contacts
an explorer, market API or third-party wallet service. The separate, explicit
`fetch_release.py` development utility contacts GitHub to download a public
daemon release; SDK calls and test execution do not perform that download.

Cookie credentials are reread per call to support rotation. Direct cookie-file
symlinks are rejected when checked. Cookie access and its parent directory must
remain protected by the OS; this is not a defense against a hostile same-user
process or a file replacement race. The SDK has no key custody of its own; a
trusted daemon may still hold private wallet keys and sign transactions.

## Controls

| Risk | Implemented control | Boundary |
| --- | --- | --- |
| Credentials forwarded by HTTP redirects | Reject all redirects; no retry | Trust the configured loopback daemon |
| Ambient proxy/DNS leakage | Direct literal IPv4 loopback connection | Does not isolate the node's own P2P network |
| Raw errors exposing addresses/paths | Fixed SDK errors, numeric RPC codes | Caller crash tools can inspect memory/locals |
| Stable hashes linking reports | Fresh optional HMAC labels per instance | Within-session labels remain linkable |
| Reused addresses / identifying wallet labels | New address per request, empty label | Customer address and on-chain transfer remain public |
| Broad wallet data retrieved for one invoice | Address-filtered receipts | Transaction detail can include other wallet entries internally |
| CI artifacts revealing fixtures | Allowlisted JSON/JUnit schemas, static IDs | Schema validation is not a universal secret detector |
| Uncertain sends duplicated by retries | No retries; explicit unknown outcome | Application must implement durable reconciliation |

`repr()` hides credentials, amounts and payment-model values. This is a guard
against incidental debug output, not encryption: `.text`, `str(amount)`, request
serialization, attributes and returned addresses/txids deliberately expose data
to the caller. Do not log them publicly or put request files into issue reports.

Read-only defaults and per-send caps are library checks, not server-side
authorization. Code that holds the same RPC credentials can bypass this SDK.
Use a dedicated OS account, protected cookie/datadir and suitable daemon RPC
permissions. Keep customer data in a separate private application database.

## Test and example lifecycle

The live suite creates synthetic wallets in a private temporary directory, binds
RPC/P2P to loopback, disables discovery/seeds/onion/UPnP and uses `connect=0`.
It launches only the verified executable, with explicit datadir/config and a
restricted child environment. Node logs and standard streams are suppressed.
Cleanup stops only its own process handles and removes its temporary tree.
An OS crash or forced kill can leave local test data; cleanup is not secure
erasure and memory, swap or crash dumps are outside this guarantee.

The delivered run used these application/node settings. Creating an additional
network namespace was denied by the execution environment, so the evidence
does **not** claim an OS-enforced egress isolation test. The Linux CI definition
runs regtest in a network namespace containing only loopback after dependency
downloads; that workflow has not been executed on GitHub as part of this build.

Examples write requests and send results to new files with POSIX mode `0600`
and do not overwrite existing files. On Windows, directory/file ACLs provide
the access control. The containing directory must already be private.

Public reports contain only approved metadata and static pass/fail case IDs.
They omit runtime timestamps, hostnames, filesystem paths, addresses, txids,
amounts, seeds, cookies and raw error messages. No wallet databases or daemon
executables are distributed in the SDK source bundle. The public test binary
SHA-256 and deterministic source file hashes are deliberate provenance data.

## Limits

WAM addresses, amounts and transaction relationships are not hidden on chain.
This SDK does not implement Tor routing, confidential amounts, mixing, PayJoin
or proof of sender anonymity. Host compromise, hostile RPC servers, malicious
Python packages, memory inspection and a globally stale/eclipsed node are outside
the trust model.

Socket timeouts limit individual blocking operations, not the total wall-clock
duration of a response delivered slowly in small chunks. The response byte cap
does not provide a full resource sandbox. Keep RPC local and trusted.

Main/test identity constants are pinned, but live validation in this release is
regtest-only. Privacy checks passing is not a production security certification.
