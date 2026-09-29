"""Exact nonnegative WAM amounts; public inputs never accept binary floats."""
from dataclasses import dataclass
from decimal import Decimal
import re

from .errors import ErrorCode, require

COIN = 100_000_000
MAX_UNITS = 22_000_000 * COIN


@dataclass(frozen=True, slots=True)
class Amount:
    units: int

    def __post_init__(self) -> None:
        require(type(self.units) is int and 0 <= self.units <= MAX_UNITS, ErrorCode.AMOUNT)

    @classmethod
    def from_wam(cls, value: str) -> "Amount":
        require(isinstance(value, str) and len(value) <= 17 and
                re.fullmatch(r"(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,8})?", value) is not None,
                ErrorCode.AMOUNT)
        whole, _, fraction = value.partition(".")
        return cls(int(whole) * COIN + int((fraction + "00000000")[:8]))

    @classmethod
    def from_rpc(cls, value: object) -> "Amount":
        # RPC monetary numbers arrive as Decimal, never float. Avoid Decimal context
        # multiplication/quantization, which could round under a caller's context.
        require(type(value) is int or isinstance(value, Decimal), ErrorCode.RESPONSE)
        d = Decimal(value)
        require(d.is_finite() and 0 <= d <= Decimal(22_000_000), ErrorCode.RESPONSE)
        require(d.as_tuple().exponent >= -32, ErrorCode.RESPONSE)
        text = format(d, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return cls.from_wam(text)

    @property
    def text(self) -> str:
        return f"{self.units // COIN}.{self.units % COIN:08d}"

    def __repr__(self) -> str:
        return "Amount(<private>)"

    def __str__(self) -> str:
        return self.text
