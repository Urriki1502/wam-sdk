"""Private workspaces and within-run pseudonyms. No persistent mapping or salt."""

import hashlib
import hmac
import os
from pathlib import Path
import secrets
import tempfile


class RunPseudonyms:
    def __init__(self):
        self._key = secrets.token_bytes(32)

    def label(self, value):
        return "item-" + hmac.new(self._key, value.encode(), hashlib.sha256).hexdigest()[:24]


class PrivateWorkspace:
    """Always newly allocated; never accepts an existing node datadir."""
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="wam-it-")
        self.path = Path(self._tmp.name)
        self.path.chmod(0o700)
        return self

    def __exit__(self, *_):
        self._tmp.cleanup()


def private_write(path, content):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


class Discard:
    """Bounded-memory sink: test/node text is never exported by the runner."""
    def write(self, value):
        return len(value)

    def flush(self):
        pass
