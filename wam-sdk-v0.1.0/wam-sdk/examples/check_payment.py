"""One point-in-time receipt lookup. A merchant must persist its own fulfillment state."""
import argparse
import json
import sys
from _common import client,read_request,safe_main,wallet


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--request",required=True);args=ap.parse_args()
    receipt=wallet(client()).observe(read_request(args.request))
    # No address, txid, memo, wallet name or amount is placed in stdout.
    print(json.dumps({"status":receipt.status,"paid_at_observed_tip":receipt.paid}))


if __name__=="__main__":sys.exit(safe_main(main))
