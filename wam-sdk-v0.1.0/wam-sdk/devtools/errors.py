"""Only fixed error codes cross the public reporting boundary."""


class HarnessError(Exception):
    def __init__(self, code):
        if code not in CODES:
            code = "INTERNAL_ERROR"
        self.code = code
        super().__init__(code)


CODES = frozenset({
    "INTERNAL_ERROR", "INVALID_ENDPOINT", "RPC_TRANSPORT", "RPC_HTTP",
    "RPC_OVERSIZE", "RPC_ENVELOPE", "RPC_REMOTE", "RPC_METHOD_DENIED",
    "RPC_CREDENTIALS", "CHAIN_MISMATCH", "BINARY_DIGEST", "BINARY_MISSING",
    "NODE_START", "NODE_TIMEOUT", "NODE_STOP", "WAIT_TIMEOUT", "TARGET_CHANGED",
    "ASSERTION_FAILED", "TEST_ERROR", "NOT_RUN", "SETUP_FAILED", "CLEANUP_FAILED",
    "REPORT_INVALID", "REPORT_EXISTS", "REPORT_WRITE", "CANCELLED",
})


class RPCError(HarnessError):
    def __init__(self, rpc_code):
        super().__init__("RPC_REMOTE")
        self.rpc_code = rpc_code
