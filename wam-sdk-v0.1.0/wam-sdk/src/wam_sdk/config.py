"""Explicit network identity, capabilities and secrets with safe representations."""
import base64
from dataclasses import dataclass, field
from enum import Enum
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from .amount import Amount
from .errors import ErrorCode, WamError, require


class Network(str, Enum):
    MAIN = "main"
    TEST = "test"
    REGTEST = "regtest"

    @property
    def genesis(self) -> str:
        return {
            Network.MAIN: "d8d3debea987b62a0934c3980d62bffbb6e16aa797d19891d4fcc9b9fb11d7e9",
            Network.TEST: "ce81c20a59a9586946d46177317658575b9d1c1fc07912b5488ab76202f59bcb",
            Network.REGTEST: "b88f3d262f285e38e184f50bf3eea1c8e615486ae67d3d9eaf0976fbd6d3d30d",
        }[self]


@dataclass(frozen=True, slots=True, repr=False)
class CookieAuth:
    path: Path

    def header(self) -> str:
        try:
            path = Path(self.path)
            require(not path.is_symlink(), ErrorCode.AUTH)
            with path.open("rb") as f:
                raw = f.read(4097).strip()
            require(2 < len(raw) <= 4096 and raw.count(b":") >= 1 and
                    not any(c in raw for c in (b"\n", b"\r", b"\x00")), ErrorCode.AUTH)
            user, password = raw.split(b":", 1)
            require(bool(user) and bool(password), ErrorCode.AUTH)
            return "Basic " + base64.b64encode(raw).decode("ascii")
        except OSError:
            raise WamError(ErrorCode.AUTH) from None

    def __repr__(self) -> str:
        return "CookieAuth(<private>)"


@dataclass(frozen=True, slots=True, repr=False)
class BasicAuth:
    username: str
    password: str

    def header(self) -> str:
        require(isinstance(self.username, str) and isinstance(self.password, str) and
                bool(self.username) and bool(self.password) and ":" not in self.username and
                len(self.username) + len(self.password) <= 4096 and
                not any(ord(c) < 32 for c in self.username + self.password), ErrorCode.AUTH)
        return "Basic " + base64.b64encode((self.username + ":" + self.password).encode()).decode()

    def __repr__(self) -> str:
        return "BasicAuth(<private>)"


@dataclass(frozen=True, slots=True)
class Config:
    url: str = field(repr=False)
    network: Network
    auth: CookieAuth | BasicAuth = field(repr=False)
    timeout: float = 10.0
    max_response_bytes: int = 4 * 1024 * 1024
    max_tip_age_seconds: int = 3600
    allow_new_addresses: bool = False
    send_limit: Amount | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        require(isinstance(self.url, str) and re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}/?", self.url) is not None,
                ErrorCode.CONFIG)
        try:
            require(1 <= urlsplit(self.url).port <= 65535, ErrorCode.CONFIG)
        except (TypeError, ValueError):
            raise WamError(ErrorCode.CONFIG) from None
        require(isinstance(self.network, Network) and isinstance(self.auth, (CookieAuth, BasicAuth)), ErrorCode.CONFIG)
        require(type(self.timeout) in (int, float) and math.isfinite(self.timeout) and 0 < self.timeout <= 120, ErrorCode.CONFIG)
        require(type(self.max_response_bytes) is int and 256 <= self.max_response_bytes <= 16 * 1024 * 1024, ErrorCode.CONFIG)
        require(type(self.max_tip_age_seconds) is int and 120 <= self.max_tip_age_seconds <= 86400, ErrorCode.CONFIG)
        require(type(self.allow_new_addresses) is bool, ErrorCode.CONFIG)
        require(self.send_limit is None or isinstance(self.send_limit, Amount) and self.send_limit.units > 0,
                ErrorCode.CONFIG)

    @classmethod
    def from_env(cls, *, allow_new_addresses: bool = False, send_limit: Amount | None = None) -> "Config":
        """No default mainnet connection, no automatic home-directory discovery."""
        try:
            url, network = os.environ["WAM_RPC_URL"], Network(os.environ["WAM_NETWORK"])
            cookie = os.environ.get("WAM_COOKIE_FILE")
            if cookie:
                auth = CookieAuth(Path(cookie))
            else:
                auth = BasicAuth(os.environ["WAM_RPC_USER"], os.environ["WAM_RPC_PASSWORD"])
            return cls(url, network, auth, allow_new_addresses=allow_new_addresses, send_limit=send_limit)
        except (KeyError, ValueError):
            raise WamError(ErrorCode.CONFIG) from None
