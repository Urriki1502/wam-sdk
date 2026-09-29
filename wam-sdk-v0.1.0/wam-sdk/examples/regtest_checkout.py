"""Self-contained payer/merchant example with a disposable real WAM daemon."""
import argparse
import json
from pathlib import Path
import sys
from _common import safe_main
from devtools.node import Node
from devtools.privacy import PrivateWorkspace
from wam_sdk import Amount,Config,CookieAuth,Network,PaymentTracker,WamClient


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--wamd",required=True);ap.add_argument("--sha256",required=True)
    args=ap.parse_args()
    with PrivateWorkspace() as ws:
        n=Node(Path(args.wamd).resolve(),args.sha256,ws.path,0)
        try:
            n.start();n.wallet("synthetic-payer");n.wallet("synthetic-merchant")
            config=Config(n.rpc.url,Network.REGTEST,CookieAuth(n.cookie_path),allow_new_addresses=True,
                          send_limit=Amount.from_wam("5"))
            sdk=WamClient(config);payer=sdk.wallet("synthetic-payer");merchant=sdk.wallet("synthetic-merchant")
            # Bootstrap IBD through the regtest-only harness before SDK usage.
            mine_to=n.rpc.wallet("synthetic-payer").call("getnewaddress",["","bech32m"])
            n.rpc.call("generatetoaddress",[110,mine_to])
            request=merchant.create_request(Amount.from_wam("1.25"),confirmations=2)
            tracker=PaymentTracker(merchant,request)
            payer.send(request.address,request.amount)
            before=tracker.refresh().status
            n.rpc.call("generatetoaddress",[2,mine_to])
            after=tracker.refresh().status
            if before!="confirming" or after!="paid" or not tracker.eligible_for_fulfillment:
                raise RuntimeError("checkout criterion not met")
            print(json.dumps({"network":"regtest","before":before,"after":after,
                              "eligible_for_fulfillment":tracker.eligible_for_fulfillment}))
        finally:n.stop()


if __name__=="__main__":sys.exit(safe_main(main))
