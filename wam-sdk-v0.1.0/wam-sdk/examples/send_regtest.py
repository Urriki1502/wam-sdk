"""Deliberately restricted to regtest. Never automatically retry after an ambiguous result."""
import argparse
import json
import os
import sys
from _common import client,read_request,safe_main,wallet
from wam_sdk import Amount,ErrorCode,Network,WamError


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--request",required=True);ap.add_argument("--limit",required=True)
    ap.add_argument("--result",required=True);args=ap.parse_args()
    c=client(send_limit=Amount.from_wam(args.limit))
    if c.config.network is not Network.REGTEST:raise WamError(ErrorCode.PERMISSION)
    request=read_request(args.request)
    if request.network is not Network.REGTEST:raise WamError(ErrorCode.NETWORK)
    # Reserve the result BEFORE sending. Repeating the same command cannot send
    # again while this file exists, even if the first process crashed mid-request.
    fd=os.open(args.result,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump({"status":"pending_reconciliation","network":"regtest"},f)
        f.flush();os.fsync(f.fileno())
        txid=wallet(c).send(request.address,request.amount)
        try:
            f.seek(0);f.truncate()
            json.dump({"status":"submitted","txid":txid,"network":"regtest"},f)
            f.flush();os.fsync(f.fileno())
        except OSError:
            raise WamError(ErrorCode.OUTCOME_UNKNOWN) from None
    print(json.dumps({"status":"submitted"}))


if __name__=="__main__":sys.exit(safe_main(main))
