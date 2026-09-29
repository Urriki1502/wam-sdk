"""Own, attest, and destroy a disposable WAM regtest process."""

import hashlib
import os
from pathlib import Path
import re
import socket
import subprocess
import time

from .errors import HarnessError
from .privacy import private_write
from .rpc import Cookie, RPC


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until(predicate, timeout=45):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.1)
    raise HarnessError("WAIT_TIMEOUT")


def verify_binary(path, digest):
    try:
        path = Path(path).resolve(strict=True)
        if not path.is_file():
            raise OSError
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HarnessError("BINARY_DIGEST")
        with path.open("rb") as f:
            actual = hashlib.file_digest(f, "sha256").hexdigest()
        if actual != digest:
            raise HarnessError("BINARY_DIGEST")
        return path
    except OSError:
        raise HarnessError("BINARY_MISSING") from None


class Node:
    def __init__(self, binary, digest, parent, index):
        self.binary, self.digest = Path(binary), digest
        self.path = Path(parent) / f"node-{index}"
        self.path.mkdir(mode=0o700)
        self.rpc_port, self.p2p_port = free_port(), free_port()
        while self.p2p_port == self.rpc_port:
            self.p2p_port = free_port()
        self.conf = self.path / "wam.conf"
        private_write(self.conf, "\n".join([
            "regtest=1", "server=1", "daemon=0", "dns=0", "dnsseed=0",
            "fixedseeds=0", "discover=0", "listenonion=0", "upnp=0", "natpmp=0",
            "listen=1", "debug=0", "printtoconsole=0", "shrinkdebugfile=0",
            "persistmempool=0", "keypool=20", "fallbackfee=0.0002", "dbcache=32",
            "par=1", "maxconnections=16", "[regtest]", "connect=0", "bind=127.0.0.1",
            "rpcbind=127.0.0.1", "rpcallowip=127.0.0.1",
            f"rpcport={self.rpc_port}", f"port={self.p2p_port}", "",
        ]))
        self.cookie_path = self.path / "regtest" / ".cookie"
        self.rpc = RPC(f"http://127.0.0.1:{self.rpc_port}", Cookie(self.cookie_path), timeout=90)
        self.process = None

    def start(self):
        verify_binary(self.binary, self.digest)
        # Explicit config/datadir prevent accidental reading of a user's ~/.wam.
        # Child environment does not inherit proxy/RPC/payment credentials.
        env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC",
                                         "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH") if k in os.environ}
        env.update({"TMPDIR": str(self.path), "TEMP": str(self.path), "TMP": str(self.path)})
        try:
            self.process = subprocess.Popen([
                str(self.binary), "-regtest", f"-datadir={self.path}", f"-conf={self.conf}",
                "-nodebuglogfile", "-printtoconsole=0",
            ], cwd=self.path, env=env, stdin=subprocess.DEVNULL,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        except OSError:
            raise HarnessError("NODE_START") from None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise HarnessError("NODE_START")
            try:
                self.rpc.attest()
                return self
            except HarnessError as exc:
                if exc.code == "CHAIN_MISMATCH":
                    self.stop()
                    raise
            time.sleep(0.1)
        self.stop()
        raise HarnessError("NODE_TIMEOUT")

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        try:
            self.rpc.call("stop")
        except HarnessError:
            # We own this Popen handle; never kill by name or touch unrelated nodes.
            self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                raise HarnessError("NODE_STOP") from None

    def wallet(self, name):
        self.rpc.call("createwallet", [name])
        return self.rpc.wallet(name)

    def connect(self, other):
        self.rpc.call("addnode", [f"127.0.0.1:{other.p2p_port}", "onetry"])
        wait_until(lambda: any(p.get("addr") == f"127.0.0.1:{other.p2p_port}"
                              and p.get("version", 0) > 0 for p in self.rpc.call("getpeerinfo")))

    def sync_with(self, other):
        wait_until(lambda: self.rpc.call("getbestblockhash") == other.rpc.call("getbestblockhash"), 90)
