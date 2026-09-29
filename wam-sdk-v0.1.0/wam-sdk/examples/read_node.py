"""Read node status without wallet access or printing peer identities."""
import json
import sys
from _common import client,safe_main


def main():
    state=client().status()
    print(json.dumps({"network":state.network.value,"blocks":state.blocks,
                      "headers":state.headers,"ready":state.ready}))


if __name__=="__main__":sys.exit(safe_main(main))
