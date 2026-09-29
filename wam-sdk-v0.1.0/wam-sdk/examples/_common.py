"""Example-only configuration and private file I/O. Not part of the installed SDK."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from wam_sdk import Config, ErrorCode, PaymentRequest, WamClient, WamError


def client(**kwargs):
    return WamClient(Config.from_env(**kwargs))


def wallet(c):
    try: name = os.environ["WAM_WALLET"]
    except KeyError: raise WamError(ErrorCode.CONFIG) from None
    return c.wallet(name)


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())


def read_request(path):
    with open(path,"rb") as f: raw=f.read(16_385)
    if len(raw)>16_384: raise WamError(ErrorCode.INPUT)
    try: return PaymentRequest.from_dict(json.loads(raw))
    except (ValueError,TypeError): raise WamError(ErrorCode.INPUT) from None


def safe_main(fn):
    try: return fn() or 0
    except WamError as exc:
        print(json.dumps({"error":exc.code.value,"outcome_unknown":exc.outcome_unknown}),file=sys.stderr)
        return 2
    except Exception:
        print('{"error":"example_failed"}',file=sys.stderr)
        return 2
