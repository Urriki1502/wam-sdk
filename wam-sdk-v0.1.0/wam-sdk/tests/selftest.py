from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from dataclasses import replace
from decimal import Decimal, localcontext
import io
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

from devtools.cases import case, require
from devtools.testing import CANARY, fake_rpc, reply
from wam_sdk import (Amount, BasicAuth, Config, CookieAuth, ErrorCode, Network,
                     PaymentRequest, PaymentTracker, SessionLabels, WamClient, WamError)
from wam_sdk.transport import Transport, encode

ADDR = "wamrt1p" + "a" * 58
TXID, TIP = "b" * 64, "c" * 64


def error(code, fn):
    try: fn()
    except WamError as exc:
        require(exc.code is code and CANARY not in str(exc) and CANARY not in repr(exc))
        return exc
    raise AssertionError("Expected safe failure")


class Backend:
    def __init__(self):
        self.chain = "regtest"; self.genesis = Network.REGTEST.genesis
        self.height = self.headers = 110; self.tip = TIP
        self.conf = 2; self.in_pool = True; self.owned = True; self.scanning = False
        self.amount = 1.25; self.duplicate = False; self.abandoned = False
        self.generated = False; self.conflict = False; self.tip_on_second = False; self.status_calls = 0
        self.extra_output = False

    def __call__(self, q):
        method = q["method"]
        if method == "getblockchaininfo":
            self.status_calls += 1
            if self.tip_on_second and self.status_calls > 1: self.tip = "d" * 64
            result = {"chain":self.chain,"blocks":self.height,"headers":self.headers,
                      "initialblockdownload":False,"bestblockhash":self.tip}
        elif method == "getblockhash": result = self.genesis
        elif method == "getwalletinfo":
            result = {"walletname":"synthetic-wallet","scanning":self.scanning,"lastprocessedblock":{"hash":self.tip}}
        elif method in ("validateaddress", "getaddressinfo"): result = {"ismine":self.owned,"isvalid":True}
        elif method == "getnewaddress": result = ADDR
        elif method == "getbalance": result = 12.125
        elif method == "sendtoaddress": result = TXID
        elif method == "listreceivedbyaddress": result = [{"address":ADDR,"txids":[TXID,TXID]}]
        elif method == "gettransaction":
            output = {"category":"receive","address":ADDR,"vout":0,"amount":self.amount}
            details = [output]
            if self.duplicate: details.append(dict(output))
            if self.conflict: details.append({**output,"amount":2})
            if self.extra_output: details.append({**output,"vout":1})
            result = {"txid":TXID,"confirmations":self.conf,"abandoned":self.abandoned,
                      "generated":self.generated,"lastprocessedblock":{"hash":self.tip},"details":details}
        elif method == "getmempoolentry":
            if not self.in_pool:
                return 500,{"jsonrpc":"2.0","id":q["id"],"error":{"code":-5,"message":CANARY}},{}
            result = {}
        else: result = None
        return reply(q, result)


@contextmanager
def setup(backend=None, **kwargs):
    backend = backend or Backend()
    with fake_rpc(backend) as (rpc,calls,cookie):
        cfg = Config(rpc.url, Network.REGTEST, CookieAuth(cookie), **kwargs)
        client = WamClient(cfg)
        yield backend,client,client.wallet("synthetic-wallet"),calls,cookie


def request(amount="1.25", confirmations=2):
    return PaymentRequest("e"*32, Network.REGTEST, ADDR, Amount.from_wam(amount), confirmations)


@case("selftest","SDK-001","WAM conversion retains one-watoshi precision and rejects floats/invalid syntax")
def exact_amount(_):
    require(Amount.from_wam("0.00000001").units == 1)
    require(Amount.from_wam("22000000").units == 2200000000000000)
    for v in (1.2,True,"NaN","Infinity","1e-8","-1","01","1.000000001","22000000.00000001"," 1"):
        error(ErrorCode.AMOUNT,lambda:Amount.from_wam(v))


@case("selftest","SDK-002","Decimal context precision cannot round RPC amounts")
def decimal_context(_):
    with localcontext() as ctx:
        ctx.prec = 2
        require(Amount.from_rpc(Decimal("12345.12345678")).text == "12345.12345678")


@case("selftest","SDK-003","JSON request encoder emits exact numeric amounts and rejects floats")
def json_amount(_):
    require(encode([Amount.from_wam("1.00000001")]) == "[1.00000001]")
    error(ErrorCode.INPUT,lambda:encode([1.2]))


@case("selftest","SDK-004","Configuration rejects DNS names, remote hosts, URL credentials and path injection")
def endpoints(_):
    for u in ("http://localhost:1","http://192.0.2.1:1","http://127.1:1","https://127.0.0.1:1",
              "http://u:p@127.0.0.1:1","http://127.0.0.1:65536","http://127.0.0.1:01",
              "http://127.0.0.1:1/a","http://127.0.0.1:1?x","http://127.0.0.1:1#x"):
        error(ErrorCode.CONFIG,lambda:Config(u,Network.REGTEST,BasicAuth("synthetic",CANARY)))


@case("selftest","SDK-005","Auth/config/request representations do not expose secrets or payment data")
def representations(_):
    auth = BasicAuth("synthetic",CANARY)
    cfg = Config("http://127.0.0.1:1234",Network.REGTEST,auth)
    text = repr((auth,cfg,CookieAuth(Path(CANARY)),request(),SessionLabels()))
    require(CANARY not in text and ADDR not in text and "1.25000000" not in text)


@case("selftest","SDK-006","Cookie rotation is applied to the next request")
def cookies(_):
    with setup() as (_,client,_,calls,cookie):
        client.status(); first=calls[-1][2]
        cookie.write_text("__cookie__:rotated-synthetic")
        client.status(); require(calls[-1][2] != first)


@case("selftest","SDK-007","Ambient proxy variables are ignored")
def proxies(_):
    with setup() as (_,client,_,calls,_):
        with patch.dict(os.environ,{"HTTP_PROXY":"http://192.0.2.1:1","http_proxy":"http://192.0.2.1:1","NO_PROXY":""}):
            require(client.status().ready)


@case("selftest","SDK-008","All HTTP redirects are rejected without contacting their destination")
def redirects(_):
    with fake_rpc(lambda q:reply(q,{})) as (destination,hits,_):
        for status in (301,302,303,307,308):
            with setup(lambda q:(status,b"",{"Location":destination.url})) as (_,client,_,_,_):
                error(ErrorCode.RESPONSE,client.status)
        require(not hits)


@case("selftest","SDK-009","RPC error bodies never appear in exceptions or stdout/stderr")
def error_privacy(_):
    def failure(q): return 500,{"jsonrpc":"2.0","id":q["id"],"error":{"code":-5,"message":CANARY}},{}
    with setup(failure) as (_,client,_,_,_):
        out=io.StringIO()
        with redirect_stdout(out),redirect_stderr(out):
            exc=error(ErrorCode.RPC,client.status)
        require(exc.rpc_code == -5 and out.getvalue() == "")
        require(CANARY not in repr(exc.__dict__))


@case("selftest","SDK-010","Malformed, duplicate-key, nonfinite and mismatched-ID responses fail closed")
def envelopes(_):
    responses=[b"not-json",b"[]",b'{"jsonrpc":"2.0","id":"wrong","result":1}',
               b'{"id":1,"id":2}',b'{"result":NaN}']
    for raw in responses:
        with setup(lambda q:(200,raw,{})) as (_,client,_,_,_):error(ErrorCode.RESPONSE,client.status)


@case("selftest","SDK-011","RPC responses are bounded by a configurable maximum size")
def size_limit(_):
    with setup(lambda q:reply(q,"x"*3000),max_response_bytes=256) as (_,client,_,_,_):
        error(ErrorCode.SIZE,client.status)


@case("selftest","SDK-012","Mainnet mismatch blocks address allocation before any mutation")
def network_mismatch(_):
    backend=Backend();backend.chain="main"
    with setup(backend,allow_new_addresses=True) as (_,_,wallet,calls,_):
        error(ErrorCode.NETWORK,wallet.new_address)
        require(not any(q[0]["method"] == "getnewaddress" for q in calls))


@case("selftest","SDK-013","Wrong genesis blocks operations despite matching chain name")
def genesis_mismatch(_):
    backend=Backend();backend.genesis="0"*64
    with setup(backend,send_limit=Amount.from_wam("1")) as (_,_,wallet,calls,_):
        error(ErrorCode.NETWORK,lambda:wallet.send(ADDR,Amount.from_wam("1")))
        require(not any(q[0]["method"] == "sendtoaddress" for q in calls))


@case("selftest","SDK-014","Read-only defaults prohibit address allocation and spending")
def read_only(_):
    with setup() as (_,_,wallet,calls,_):
        error(ErrorCode.PERMISSION,wallet.new_address)
        error(ErrorCode.PERMISSION,lambda:wallet.send(ADDR,Amount.from_wam("1")))
        require(not calls)


@case("selftest","SDK-015","Send cap is enforced before transport and exact amounts reach the wire")
def capped_send(_):
    with setup(send_limit=Amount.from_wam("2")) as (_,_,wallet,calls,_):
        error(ErrorCode.AMOUNT,lambda:wallet.send(ADDR,Amount.from_wam("3")))
        require(not calls)
        require(wallet.send(ADDR,Amount.from_wam("1.00000001")) == TXID)
        sent=[q[0] for q in calls if q[0]["method"]=="sendtoaddress"]
        require(len(sent)==1 and str(sent[0]["params"][1])=="1.00000001")


@case("selftest","SDK-016","Ambiguous mutation response returns outcome_unknown and is never retried")
def unknown_send(_):
    backend=Backend()
    def respond(q):
        if q["method"]=="sendtoaddress":return 200,b"broken response",{}
        return backend(q)
    with setup(respond,send_limit=Amount.from_wam("2")) as (_,_,wallet,calls,_):
        exc=error(ErrorCode.OUTCOME_UNKNOWN,lambda:wallet.send(ADDR,Amount.from_wam("1")))
        require(exc.outcome_unknown and sum(q[0]["method"]=="sendtoaddress" for q in calls)==1)


@case("selftest","SDK-017","Wallet names are percent-encoded in the RPC route")
def wallet_route(_):
    with setup() as (_,client,_,calls,_):
        Transport(client.config).call("getwalletinfo",[],wallet="synthetic /?#")
        require(calls[-1][1]=="/wallet/synthetic%20%2F%3F%23")


@case("selftest","SDK-018","Inconsistent block/header telemetry and wallet scanning block readiness")
def readiness(_):
    for field,value in (("headers",109),("scanning",{"progress":0.1})):
        backend=Backend();setattr(backend,field,value)
        with setup(backend,allow_new_addresses=True) as (_,_,wallet,calls,_):
            error(ErrorCode.NOT_READY,wallet.new_address)


@case("selftest","SDK-019","Receipt sums outputs exactly, deduplicates outpoints and respects confirmations")
def output_accounting(_):
    backend=Backend();backend.duplicate=True;backend.conf=1
    with setup(backend) as (_,_,wallet,_,_):
        r=wallet.observe(request());require(r.received.text=="1.25000000" and not r.paid and r.status=="confirming")
        backend.conf=2;backend.extra_output=True
        r=wallet.observe(request());require(r.confirmed.text=="2.50000000" and len(r.outputs)==2)


@case("selftest","SDK-020","Conflicting duplicate output evidence fails atomically")
def conflicting_outputs(_):
    backend=Backend();backend.conflict=True
    with setup(backend) as (_,_,wallet,_,_):error(ErrorCode.SNAPSHOT,lambda:wallet.observe(request()))


@case("selftest","SDK-021","Mempool eviction, abandoned transactions and coinbase do not count as payments")
def excluded_receipts(_):
    for field,value in (("abandoned",True),("generated",True),("conf",-1)):
        backend=Backend();setattr(backend,field,value)
        with setup(backend) as (_,_,wallet,_,_):require(wallet.observe(request()).received.units==0)
    backend=Backend();backend.conf=0;backend.in_pool=False
    with setup(backend) as (_,_,wallet,_,_):require(wallet.observe(request()).received.units==0)


@case("selftest","SDK-022","A tip change during receipt scanning invalidates the snapshot")
def changing_tip(_):
    backend=Backend();backend.tip_on_second=True
    with setup(backend) as (_,_,wallet,_,_):error(ErrorCode.SNAPSHOT,lambda:wallet.observe(request()))


@case("selftest","SDK-023","Unowned addresses and cross-network payment requests are rejected")
def request_ownership(_):
    backend=Backend();backend.owned=False
    with setup(backend) as (_,_,wallet,_,_):
        error(ErrorCode.INPUT,lambda:wallet.observe(request()))
        error(ErrorCode.NETWORK,lambda:wallet.observe(replace(request(),network=Network.MAIN)))


@case("selftest","SDK-024","Tracker latches review after a previously confirmed payment loses confirmations")
def reorg_latch(_):
    with setup() as (backend,_,wallet,_,_):
        tracker=PaymentTracker(wallet,request());tracker.refresh();require(tracker.eligible_for_fulfillment)
        backend.conf=0;tracker.refresh();require(tracker.needs_review and not tracker.eligible_for_fulfillment)
        backend.conf=2;tracker.refresh();require(tracker.needs_review and not tracker.eligible_for_fulfillment)


@case("selftest","SDK-025","An outage preserves the last receipt while disabling fulfillment")
def outage(_):
    with setup() as (backend,_,wallet,_,_):
        tracker=PaymentTracker(wallet,request());previous=tracker.refresh()
        backend.headers=109
        error(ErrorCode.NOT_READY,tracker.refresh)
        require(tracker.receipt is previous and not tracker.eligible_for_fulfillment)


@case("selftest","SDK-026","Freshness uses monotonic time and expires without a new poll")
def stale(_):
    with setup() as (_,_,wallet,_,_):
        tracker=PaymentTracker(wallet,request(),freshness_seconds=5)
        with patch("wam_sdk.payments.time.monotonic",return_value=10):tracker.refresh()
        with patch("wam_sdk.payments.time.monotonic",return_value=16):require(not tracker.eligible_for_fulfillment)


@case("selftest","SDK-027","Payment request serialization round-trips and rejects unknown fields")
def request_roundtrip(_):
    req=request();require(PaymentRequest.from_dict(req.to_dict())==req)
    error(ErrorCode.INPUT,lambda:PaymentRequest.from_dict({**req.to_dict(),"secret":CANARY}))


@case("selftest","SDK-028","Session pseudonyms cannot link the same value across independent sessions")
def session_labels(_):
    a,b=SessionLabels(),SessionLabels()
    require(a.label(CANARY)==a.label(CANARY) and a.label(CANARY)!=b.label(CANARY))


@case("selftest","SDK-029","Concurrent reads use separate connections and unique request IDs")
def concurrent_reads(_):
    with setup() as (_,client,_,calls,_):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:client.status(),range(12)))
        ids=[q[0]["id"] for q in calls]
        require(all(x.ready for x in results) and len(set(ids))==len(ids))


@case("selftest","SDK-030","Invalid or missing authentication is rejected without sending a request")
def bad_auth(_):
    with setup() as (_,client,_,calls,cookie):
        cookie.write_text("invalid-cookie")
        error(ErrorCode.AUTH,client.status);require(not calls)


@case("selftest","SDK-031","SDK-generated addresses use empty labels and Taproot by default")
def address_labels(_):
    with setup(allow_new_addresses=True) as (_,_,wallet,calls,_):
        require(wallet.new_address()==ADDR)
        require([q[0]["params"] for q in calls if q[0]["method"]=="getnewaddress"]==[["","bech32m"]])


@case("selftest","SDK-032","Socket timeouts are safe read errors or ambiguous mutations without automatic retry")
def socket_timeouts(_):
    backend=Backend()
    def respond(q):
        if q["method"] in ("getbalance","sendtoaddress"):
            time.sleep(0.3)
        return backend(q)
    with setup(respond,timeout=0.1,send_limit=Amount.from_wam("2")) as (_,_,wallet,calls,_):
        error(ErrorCode.TIMEOUT,wallet.balance)
        error(ErrorCode.OUTCOME_UNKNOWN,lambda:wallet.send(ADDR,Amount.from_wam("1")))
        require(sum(q[0]["method"]=="sendtoaddress" for q in calls)==1)


@case("selftest","SDK-033","Payment polling requests only the invoice address and review latch is read-only")
def narrow_receipt_query(_):
    with setup() as (_,_,wallet,calls,_):
        tracker=PaymentTracker(wallet,request());tracker.refresh()
        require([q[0]["params"] for q in calls if q[0]["method"]=="listreceivedbyaddress"]
                ==[[0,False,True,ADDR]])
        try:tracker.needs_review=False
        except AttributeError:pass
        else:raise AssertionError("Review latch should be read-only")
