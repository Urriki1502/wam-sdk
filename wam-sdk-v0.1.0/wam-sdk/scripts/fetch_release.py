#!/usr/bin/env python3
"""Explicit download step; test runs themselves never fetch code or contact services."""
import hashlib
import io
import os
from pathlib import Path
import sys
import tarfile
import urllib.request

ARCHIVE = "wam-coin-v0.1.11-x86_64-linux-gnu.tar.gz"
URL = "https://github.com/wamcoin-core-dev/wam-coin/releases/download/v0.1.11/" + ARCHIVE
ARCHIVE_SHA256 = "bd010ed615ab8063d5c12aa61236311ece7e9d19896d9541dacba1888dd9987a"
BINARY_SHA256 = "625609c08afef441e9dddd71330dcab1cec112d6fabe361769b9907f0efe7ab4"


def main():
    destination = Path(__file__).resolve().parents[1] / ".tools" / "wamd"
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != BINARY_SHA256:
            raise ValueError
        print("Pinned Linux daemon already available")
        return
    # No ambient proxy credentials; never add Authorization headers.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL, timeout=60) as response:
        archive = response.read(20 * 1024 * 1024 + 1)
    if len(archive) > 20 * 1024 * 1024 or hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA256:
        raise ValueError
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        # Extract exactly one regular member to a fixed path; never extract archive paths.
        members = [m for m in tar.getmembers() if m.name == "wam-coin-v0.1.11/bin/wamd"]
        if len(members) != 1 or not members[0].isfile() or members[0].size > 40 * 1024 * 1024:
            raise ValueError
        data = tar.extractfile(members[0]).read()
    if hashlib.sha256(data).hexdigest() != BINARY_SHA256:
        raise ValueError
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    with os.fdopen(fd, "wb") as f: f.write(data)
    print("Pinned Linux daemon downloaded and checksum verified")


if __name__ == "__main__":
    try: main()
    except Exception:
        print("Release download or checksum verification failed", file=sys.stderr)
        sys.exit(2)
