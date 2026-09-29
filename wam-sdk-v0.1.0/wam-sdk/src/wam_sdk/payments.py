"""In-memory payment freshness and reorg latch; durable business state belongs to the app."""
import time
from .client import Wallet
from .errors import ErrorCode, require
from .models import PaymentReceipt, PaymentRequest


class PaymentTracker:
    def __init__(self, wallet: Wallet, request: PaymentRequest, *, freshness_seconds: int = 30):
        require(type(freshness_seconds) is int and 1 <= freshness_seconds <= 3600, ErrorCode.INPUT)
        self._wallet, self._request = wallet, request
        self._freshness = freshness_seconds
        self._receipt: PaymentReceipt | None = None
        self._known: set[str] = set()
        self._at: float | None = None
        self._healthy = False
        self._ever_paid = False
        self._needs_review = False

    @property
    def needs_review(self) -> bool:
        return self._needs_review

    @property
    def receipt(self) -> PaymentReceipt | None:
        return self._receipt

    def refresh(self) -> PaymentReceipt:
        self._healthy = False
        receipt = self._wallet.observe(self._request, tuple(sorted(self._known)))
        self._known.update(receipt.txids)
        if self._ever_paid and not receipt.paid:
            self._needs_review = True
        self._ever_paid = self._ever_paid or receipt.paid
        self._receipt, self._at, self._healthy = receipt, time.monotonic(), True
        return receipt

    @property
    def eligible_for_fulfillment(self) -> bool:
        fresh = self._at is not None and 0 <= time.monotonic() - self._at <= self._freshness
        return bool(self._healthy and fresh and self._receipt and self._receipt.paid and not self.needs_review)


# Deliberately no public reset-review method: business review must be an explicit,
# durable application decision, not an accidental "clear flags" convenience call.
