from dataclasses import replace
from pathlib import Path
import json
import os
import subprocess
import sys

from devtools.cases import case,require
from devtools.node import Node
from devtools.privacy import PrivateWorkspace
from wam_sdk import Amount,Config,CookieAuth,ErrorCode,Network,PaymentTracker,WamClient
from tests.selftest import error

ROOT=Path(__file__).resolve().parents[1]


class Live:
    def __init__(self,binary,digest):self.binary,self.digest=binary,digest
    def __enter__(self):
        self.ws=PrivateWorkspace();self.ws.__enter__();self.path=self.ws.path
        self.node=Node(self.binary,self.digest,self.path,0)
        try:
            self.node.start();self.node.wallet("synthetic-payer")
            self.config=Config(self.node.rpc.url,Network.REGTEST,CookieAuth(self.node.cookie_path),
                               allow_new_addresses=True,send_limit=Amount.from_wam("10"))
            self.client=WamClient(self.config);self.payer=self.client.wallet("synthetic-payer")
            # A genesis-only chain is still in IBD. Bootstrap through the
            # isolated regtest harness; the SDK correctly requires readiness.
            self.mine_to=self.node.rpc.wallet("synthetic-payer").call("getnewaddress",["","bech32m"])
            self.counter=0
            self.mine(110)
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def __exit__(self,*_):
        try:self.node.stop()
        finally:self.ws.__exit__(None,None,None)
    def mine(self,n=1):return self.node.rpc.call("generatetoaddress",[n,self.mine_to])
    def merchant(self):
        self.counter+=1;name=f"synthetic-merchant-{self.counter}"
        self.node.wallet(name)
        return name,self.client.wallet(name)
    def send(self,request,amount=None):return self.payer.send(request.address,amount or request.amount)
    def env(self,wallet):
        env={k:os.environ[k] for k in ("PATH","SYSTEMROOT","WINDIR","LD_LIBRARY_PATH") if k in os.environ}
        env.update({"PYTHONPATH":str(ROOT/"src"),"WAM_RPC_URL":self.node.rpc.url,"WAM_NETWORK":"regtest",
                    "WAM_COOKIE_FILE":str(self.node.cookie_path),"WAM_WALLET":wallet})
        return env
    def example(self,name,*args,wallet="synthetic-payer"):
        return subprocess.run([sys.executable,str(ROOT/"examples"/name),*map(str,args)],
                              env=self.env(wallet),capture_output=True,text=True,timeout=90)


@case("regtest","LIVE-001","Read actual WAM chain identity and typed supply figures")
def chain(c):
    s=c.client.status();require(s.ready and s.network is Network.REGTEST)
    supply=c.client.supply();require(supply["max_supply"].text=="22000000.00000000")


@case("regtest","LIVE-002","Generate distinct real Taproot receive addresses without customer labels")
def addresses(c):
    name,w=c.merchant();addresses=[w.new_address() for _ in range(8)]
    require(len(set(addresses))==8)
    for a in addresses:
        i=c.node.rpc.wallet(name).call("getaddressinfo",[a])
        require(a.startswith("wamrt1p") and i["witness_version"]==1 and i["ismine"])
        require(all(x in ("",{"name":"","purpose":"receive"}) for x in i.get("labels",[])))


@case("regtest","LIVE-003","Exact SDK send and receipt transitions through zero, one and two confirmations")
def payment(c):
    _,w=c.merchant();req=w.create_request(Amount.from_wam("1.00000001"),2);tracker=PaymentTracker(w,req)
    c.send(req);r=tracker.refresh();require(r.status=="confirming" and r.received.text=="1.00000001")
    c.mine();tracker.refresh();require(not tracker.eligible_for_fulfillment)
    c.mine();tracker.refresh();require(tracker.eligible_for_fulfillment)


@case("regtest","LIVE-004","Multiple real payments accumulate without duplicate accounting")
def partial(c):
    _,w=c.merchant();req=w.create_request(Amount.from_wam("2"),2)
    c.send(req,Amount.from_wam("0.5"));c.mine(2);require(w.observe(req).status=="partial")
    c.send(req,Amount.from_wam("1.75"));c.mine(2)
    a=w.observe(req);b=w.observe(req)
    require(a.confirmed.text=="2.25000000" and b.confirmed==a.confirmed and len(a.outputs)==2)


@case("regtest","LIVE-005","Real chain invalidation revokes fulfillment and review remains latched after restoration")
def reorg(c):
    _,w=c.merchant();req=w.create_request(Amount.from_wam("1"),2);tracker=PaymentTracker(w,req)
    c.send(req);blocks=c.mine(2);tracker.refresh();require(tracker.eligible_for_fulfillment)
    try:
        c.node.rpc.call("invalidateblock",[blocks[0]])
        tracker.refresh();require(tracker.needs_review and not tracker.eligible_for_fulfillment)
    finally:
        c.node.rpc.call("reconsiderblock",[blocks[0]])
        c.mine() # Independently asserted transient telemetry mismatch in LIVE-006.
    tracker.refresh();require(tracker.needs_review and not tracker.eligible_for_fulfillment)


@case("regtest","LIVE-006","SDK fails closed when WAM v0.1.11 reports stale header height after reconsiderblock")
def reconsider_contract(c):
    name,w=c.merchant();blocks=c.mine(2)
    try:
        c.node.rpc.call("invalidateblock",[blocks[0]])
        c.node.rpc.call("reconsiderblock",[blocks[0]])
        status=c.client.status()
        # This is an SDK fail-closed regression for the previously measured Core
        # behavior, not a claim that the upstream behavior has been fixed.
        require(status.blocks!=status.headers and not status.ready)
        error(ErrorCode.NOT_READY,w.new_address)
    finally:
        c.node.rpc.call("reconsiderblock",[blocks[0]]);c.mine()
    require(c.client.status().ready)


@case("regtest","LIVE-007","Node restart rotates auth and failed polling disables fulfillment without erasing the receipt")
def restart(c):
    name,w=c.merchant();req=w.create_request(Amount.from_wam("1"),2);tracker=PaymentTracker(w,req)
    c.send(req);c.mine(2);previous=tracker.refresh();cookie=c.node.cookie_path.read_bytes()
    c.node.stop()
    try:
        # Cookie disappears on orderly shutdown; either auth or transport can fail.
        try:tracker.refresh()
        except Exception:pass
        require(not tracker.eligible_for_fulfillment and tracker.receipt is previous)
    finally:
        c.node.start()
        for wallet in ("synthetic-payer",name):
            if wallet not in c.node.rpc.call("listwallets"):c.node.rpc.call("loadwallet",[wallet])
    require(c.node.cookie_path.read_bytes()!=cookie)
    tracker.refresh();require(tracker.eligible_for_fulfillment)


@case("regtest","LIVE-008","Balance is an exact Amount from a real descriptor wallet")
def balance(c):
    require(isinstance(c.payer.balance(),Amount) and c.payer.balance().units>0)


@case("regtest","LIVE-009","Read-only configuration refuses spend even with a funded real wallet")
def spending_disabled(c):
    read_only=WamClient(replace(c.config,send_limit=None)).wallet("synthetic-payer")
    before=c.payer.balance()
    error(ErrorCode.PERMISSION,lambda:read_only.send(c.mine_to,Amount.from_wam("1")))
    require(c.payer.balance()==before)


@case("regtest","LIVE-010","Node-status example executes and exports only minimal node metadata")
def read_example(c):
    p=c.example("read_node.py");require(p.returncode==0 and not p.stderr)
    result=json.loads(p.stdout);require(set(result)=={"network","blocks","headers","ready"} and result["ready"])


@case("regtest","LIVE-011","Create/check examples work through private payment-request files")
def receiving_examples(c):
    name,w=c.merchant();path=c.path/"payment-request.json"
    p=c.example("create_payment_request.py","--amount","1.25","--confirmations","2","--output",path,wallet=name)
    require(p.returncode==0 and json.loads(p.stdout)=={"status":"request_created"})
    from wam_sdk import PaymentRequest
    req=PaymentRequest.from_dict(json.loads(path.read_text()))
    if os.name=="posix":require(path.stat().st_mode&0o077==0)
    c.send(req);c.mine(2)
    p=c.example("check_payment.py","--request",path,wallet=name)
    require(p.returncode==0 and json.loads(p.stdout)=={"status":"paid","paid_at_observed_tip":True})
    require(req.address not in p.stdout)


@case("regtest","LIVE-012","Send example submits once and refuses reuse of the same result path before resending")
def send_example(c):
    name,w=c.merchant();req=w.create_request(Amount.from_wam("0.5"),1)
    request_path=c.path/"send-request.json";result_path=c.path/"send-result.json"
    request_path.write_text(json.dumps(req.to_dict()));request_path.chmod(0o600)
    args=("--request",request_path,"--limit","1","--result",result_path)
    first=c.example("send_regtest.py",*args);require(first.returncode==0)
    second=c.example("send_regtest.py",*args);require(second.returncode!=0)
    c.mine();receipt=w.observe(req)
    require(receipt.confirmed.text=="0.50000000" and len(receipt.outputs)==1)
    require(req.address not in first.stdout and "txid" not in first.stdout)


@case("regtest","LIVE-013","Self-contained checkout example completes against its own fresh daemon")
def checkout_example(c):
    p=c.example("regtest_checkout.py","--wamd",c.binary,"--sha256",c.digest)
    require(p.returncode==0)
    data=json.loads(p.stdout)
    require(data=={"network":"regtest","before":"confirming","after":"paid","eligible_for_fulfillment":True})
