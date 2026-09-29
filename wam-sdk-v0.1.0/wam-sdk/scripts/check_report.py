#!/usr/bin/env python3
"""Validate public evidence before any artifact upload."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devtools.report import scan_public

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError
        scan_public(sys.argv[1])
        print("Public report schema valid")
    except Exception:
        print("Public report rejected", file=sys.stderr)
        sys.exit(2)
