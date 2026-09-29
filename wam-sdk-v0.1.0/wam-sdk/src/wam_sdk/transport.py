"""Direct loopback HTTP. No retries, redirects, proxy, logging or shared connection."""
import http.client
import json
import socket
import uuid
from decimal import Decimal
from urllib.parse import quote, urlsplit

from .amount import Amount
from .config import Config
from .errors import ErrorCode, WamError, require


def encode(value: object, depth: int = 0) -> str:
    """Exact JSON numeric encoding: Amount is emitted as a decimal, never a float."""
    require(depth <= 32, ErrorCode.INPUT)
    if isinstance(value, Amount): return value.text
    if value is None: return "null"
    if type(value) is bool: return "true" if value else "false"
    if type(value) is int: return str(value)
    if isinstance(value, str): return json.dumps(value, ensure_ascii=True)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(encode(v, depth + 1) for v in value) + "]"
    if isinstance(value, dict):
        require(all(isinstance(k, str) for k in value), ErrorCode.INPUT)
        return "{" + ",".join(encode(k) + ":" + encode(v, depth + 1) for k,v in value.items()) + "}"
    raise WamError(ErrorCode.INPUT)


def unique(pairs):
    result = {}
    for k,v in pairs:
        if k in result: raise ValueError
        result[k] = v
    return result


def reject_constant(_):
    raise ValueError


class Transport:
    """Internal transport; use WamClient's typed public methods for chain checks."""
    def __init__(self, config: Config):
        self.config = config

    def call(self, method: str, params: list, *, wallet: str | None = None,
             mutation: bool = False):
        cfg = self.config
        ident = uuid.uuid4().hex
        body = encode({"jsonrpc":"2.0", "id":ident, "method":method, "params":params}).encode()
        require(len(body) <= 256_000, ErrorCode.INPUT)
        auth = cfg.auth.header()  # Authentication failures happen before a request is attempted.
        path = "/" if wallet is None else "/wallet/" + quote(wallet, safe="")
        conn = http.client.HTTPConnection("127.0.0.1", urlsplit(cfg.url).port, timeout=cfg.timeout)
        attempted = False
        try:
            attempted = True
            conn.request("POST", path, body=body, headers={"Content-Type":"application/json", "Authorization":auth})
            response = conn.getresponse()
            if response.status == 401:
                raise WamError(ErrorCode.AUTH)
            require(response.status in (200, 400, 404, 500), ErrorCode.RESPONSE)
            raw = response.read(cfg.max_response_bytes + 1)
            require(len(raw) <= cfg.max_response_bytes, ErrorCode.SIZE)
            try:
                result = json.loads(raw, parse_float=Decimal, parse_constant=reject_constant, object_pairs_hook=unique)
            except (ValueError, UnicodeError, RecursionError):
                raise WamError(ErrorCode.RESPONSE) from None
            require(isinstance(result, dict) and result.get("jsonrpc") == "2.0" and result.get("id") == ident)
            if result.get("error") is not None:
                error = result["error"]
                require(isinstance(error, dict) and type(error.get("code")) is int and result.get("result") is None)
                raise WamError(ErrorCode.RPC, error["code"])
            require(response.status == 200 and "result" in result)
            return result["result"]
        except WamError as exc:
            # Invalid/oversized/redirected mutation responses cannot prove the RPC
            # did not run. The caller must reconcile before considering another send.
            if mutation and attempted and exc.code not in (ErrorCode.AUTH, ErrorCode.RPC):
                raise WamError(ErrorCode.OUTCOME_UNKNOWN) from None
            raise
        except socket.timeout:
            code = ErrorCode.OUTCOME_UNKNOWN if mutation and attempted else ErrorCode.TIMEOUT
            raise WamError(code) from None
        except (OSError, http.client.HTTPException, ValueError):
            code = ErrorCode.OUTCOME_UNKNOWN if mutation and attempted else ErrorCode.TRANSPORT
            raise WamError(code) from None
        finally:
            conn.close()
