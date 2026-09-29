"""Create a fresh receive address; write sensitive payment details to a new private file."""
import argparse
import json
import sys
from _common import client,safe_main,wallet,write_private
from wam_sdk import Amount


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--amount",required=True)
    ap.add_argument("--confirmations",type=int,default=6)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    req=wallet(client(allow_new_addresses=True)).create_request(Amount.from_wam(args.amount),args.confirmations)
    write_private(args.output,req.to_dict())
    print(json.dumps({"status":"request_created"}))


if __name__=="__main__":sys.exit(safe_main(main))
