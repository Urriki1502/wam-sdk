"""Stable public error codes. Node messages, credentials and parameters are never retained."""
from enum import Enum


class ErrorCode(str, Enum):
    CONFIG = "invalid_configuration"
    AMOUNT = "invalid_amount"
    INPUT = "invalid_input"
    AUTH = "authentication_failed"
    TRANSPORT = "transport_failed"
    TIMEOUT = "request_timeout"
    RESPONSE = "invalid_rpc_response"
    SIZE = "response_too_large"
    RPC = "rpc_rejected"
    NETWORK = "network_mismatch"
    NOT_READY = "node_or_wallet_not_ready"
    SNAPSHOT = "inconsistent_snapshot"
    PERMISSION = "operation_not_enabled"
    OUTCOME_UNKNOWN = "mutation_outcome_unknown"


class WamError(Exception):
    """Safe to print; raw upstream error text is deliberately unavailable."""
    def __init__(self, code: ErrorCode, rpc_code: int | None = None):
        self.code = code
        self.rpc_code = rpc_code
        self.outcome_unknown = code is ErrorCode.OUTCOME_UNKNOWN
        super().__init__(code.value)


def require(condition: bool, code: ErrorCode = ErrorCode.RESPONSE) -> None:
    if not condition:
        raise WamError(code)
