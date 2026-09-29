#!/usr/bin/env python3
"""Private evidence runner; never serializes RPC data or raw assertion messages."""
import argparse
import contextlib
from pathlib import Path
import signal
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"src"))
sys.dont_write_bytecode=True

from devtools.cases import CATALOG,suite
from devtools.errors import HarnessError
from devtools.privacy import Discard
from devtools.report import SafeResult,build_report,write_report,scan_public


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("profile",choices=("selftest","regtest"))
    ap.add_argument("--wamd");ap.add_argument("--sha256")
    ap.add_argument("--report-dir",required=True);args=ap.parse_args()
    import tests.selftest,tests.integration
    result=SafeResult();code=None;digest=None
    def interrupt(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupt)
    if Path(args.report_dir).exists():raise HarnessError("REPORT_EXISTS")
    try:
        with contextlib.redirect_stdout(Discard()),contextlib.redirect_stderr(Discard()):
            if args.profile=="selftest":suite("selftest").run(result)
            else:
                from devtools.node import verify_binary
                from tests.integration import Live
                if not args.wamd or not args.sha256:raise HarnessError("BINARY_MISSING")
                binary=verify_binary(args.wamd,args.sha256);digest=args.sha256
                with Live(binary,digest) as live:suite("regtest",live).run(result)
    except KeyboardInterrupt:code="CANCELLED"
    except HarnessError as exc:code=exc.code
    except Exception:code="SETUP_FAILED"
    done={r["id"] for r in result.rows}
    result.rows += [{"id":ident,"status":"not_run","code":"NOT_RUN"}
                   for ident,_,_ in CATALOG[args.profile] if ident not in done]
    report=build_report(result.rows,args.profile,digest,code)
    write_report(args.report_dir,report);scan_public(args.report_dir)
    print(args.profile,report["counts"])
    for row in result.rows:
        if row["status"]!="pass":print(row["id"],row["status"],row["code"])
    if code:print("Run error:",code)
    return 0 if report["verdict"]=="pass" else 2 if code or report["counts"]["error"] or report["counts"]["not_run"] else 1


if __name__=="__main__":
    try:sys.exit(main())
    except Exception:print("Harness failed",file=sys.stderr);sys.exit(2)
