"""Opt-in within-session pseudonyms; no stable hash of an address or wallet name."""
import hashlib
import hmac
import secrets


class SessionLabels:
    def __init__(self):
        self.__key = secrets.token_bytes(32)

    def label(self, value: str) -> str:
        return "item-" + hmac.new(self.__key, value.encode(), hashlib.sha256).hexdigest()[:24]

    def __repr__(self) -> str:
        return "SessionLabels(<private>)"
