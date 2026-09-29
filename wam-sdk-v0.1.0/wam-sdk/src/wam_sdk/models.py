from dataclasses import dataclass
import re

from .amount import Amount
from .config import Network
from .errors import ErrorCode, require


@dataclass(frozen=True, slots=True)
class NodeStatus:
    network: Network
    blocks: int
    headers: int
    initial_download: bool
    tip: str
    ready: bool


@dataclass(frozen=True, slots=True, repr=False)
class PaymentRequest:
    id: str
    network: Network
    address: str
    amount: Amount
    confirmations: int = 6

    def __post_init__(self):
        require(isinstance(self.id, str) and re.fullmatch(r"[0-9a-f]{32}", self.id) is not None, ErrorCode.INPUT)
        require(isinstance(self.network, Network), ErrorCode.INPUT)
        require(isinstance(self.address, str) and re.fullmatch(r"[A-Za-z0-9]{14,128}", self.address) is not None, ErrorCode.INPUT)
        require(isinstance(self.amount, Amount) and self.amount.units > 0, ErrorCode.AMOUNT)
        require(type(self.confirmations) is int and 1 <= self.confirmations <= 1000, ErrorCode.INPUT)

    def to_dict(self) -> dict:
        """Explicit sensitive serialization; do not put this in public CI logs."""
        return {"schema":1, "id":self.id, "network":self.network.value, "address":self.address,
                "amount":self.amount.text, "confirmations":self.confirmations}

    @classmethod
    def from_dict(cls, data: dict) -> "PaymentRequest":
        require(isinstance(data, dict) and set(data) == {"schema","id","network","address","amount","confirmations"}
                and type(data["schema"]) is int and data["schema"] == 1, ErrorCode.INPUT)
        try:
            return cls(data["id"], Network(data["network"]), data["address"],
                       Amount.from_wam(data["amount"]), data["confirmations"])
        except (ValueError, TypeError):
            from .errors import WamError
            raise WamError(ErrorCode.INPUT) from None


@dataclass(frozen=True, slots=True, repr=False)
class PaymentOutput:
    txid: str
    vout: int
    amount: Amount
    confirmations: int


@dataclass(frozen=True, slots=True, repr=False)
class PaymentReceipt:
    request: PaymentRequest
    tip: str
    height: int
    outputs: tuple[PaymentOutput, ...]

    @property
    def received(self) -> Amount:
        return Amount(sum(p.amount.units for p in self.outputs))

    @property
    def confirmed(self) -> Amount:
        return Amount(sum(p.amount.units for p in self.outputs if p.confirmations >= self.request.confirmations))

    @property
    def paid(self) -> bool:
        """A point-in-time observation, not a permanent fulfillment decision."""
        return self.confirmed.units >= self.request.amount.units

    @property
    def status(self) -> str:
        if self.paid: return "paid"
        if self.received.units >= self.request.amount.units: return "confirming"
        return "partial" if self.received.units else "pending"

    @property
    def txids(self) -> tuple[str, ...]:
        return tuple(sorted({p.txid for p in self.outputs}))
