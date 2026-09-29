"""Typed, chain-pinned node and wallet operations for the WAM v0.1.11 RPC family."""
import re
import time
import uuid

from .amount import Amount
from .config import Config, Network
from .errors import ErrorCode, WamError, require
from .models import NodeStatus, PaymentOutput, PaymentReceipt, PaymentRequest
from .transport import Transport

HASH = re.compile(r"[0-9a-f]{64}")


def hash_value(value) -> str:
    require(isinstance(value, str) and HASH.fullmatch(value) is not None)
    return value


def address_value(value) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9]{14,128}", value) is not None, ErrorCode.INPUT)
    return value


class WamClient:
    def __init__(self, config: Config):
        require(isinstance(config, Config), ErrorCode.CONFIG)
        self.config = config
        self._transport = Transport(config)

    def status(self) -> NodeStatus:
        info = self._transport.call("getblockchaininfo", [])
        require(isinstance(info, dict))
        genesis = self._transport.call("getblockhash", [0])
        require(info.get("chain") == self.config.network.value and genesis == self.config.network.genesis, ErrorCode.NETWORK)
        blocks, headers, ibd = info.get("blocks"), info.get("headers"), info.get("initialblockdownload")
        require(type(blocks) is int and type(headers) is int and min(blocks,headers) >= 0 and type(ibd) is bool)
        tip = hash_value(info.get("bestblockhash"))
        ready = not ibd and blocks == headers
        if self.config.network is not Network.REGTEST:
            header = self._transport.call("getblockheader", [tip])
            peers = self._transport.call("getconnectioncount", [])
            require(isinstance(header, dict) and type(header.get("time")) is int and type(peers) is int)
            age = time.time() - header["time"]
            ready = ready and peers > 0 and -7200 <= age <= self.config.max_tip_age_seconds
        return NodeStatus(self.config.network, blocks, headers, ibd, tip, ready)

    def supply(self) -> dict[str, Amount | int]:
        self.status()
        raw = self._transport.call("getsupplyinfo", [])
        require(isinstance(raw, dict) and type(raw.get("height")) is int)
        result = {"height":raw["height"]}
        for key in ("circulating", "max_supply", "premine", "block_subsidy"):
            value = raw.get(key)
            result[key] = Amount.from_wam(value) if isinstance(value, str) else Amount.from_rpc(value)
        return result

    def wallet(self, name: str) -> "Wallet":
        require(isinstance(name, str) and 0 < len(name) <= 128 and not any(ord(c) < 32 for c in name), ErrorCode.INPUT)
        return Wallet(self, name)

    def _ready(self, wallet: str) -> NodeStatus:
        status = self.status()
        require(status.ready, ErrorCode.NOT_READY)
        self._wallet_ready(wallet, status.tip)
        return status

    def _wallet_ready(self, wallet: str, tip: str) -> None:
        info = self._transport.call("getwalletinfo", [], wallet=wallet)
        require(isinstance(info, dict))
        require(info.get("walletname") == wallet and info.get("scanning") is False and
                isinstance(info.get("lastprocessedblock"), dict) and
                info["lastprocessedblock"].get("hash") == tip, ErrorCode.NOT_READY)


class Wallet:
    def __init__(self, client: WamClient, name: str):
        self._client, self._name = client, name

    def balance(self, min_confirmations: int = 1) -> Amount:
        require(type(min_confirmations) is int and 0 <= min_confirmations <= 1000, ErrorCode.INPUT)
        before = self._client._ready(self._name)
        result = self._client._transport.call("getbalance", ["*", min_confirmations], wallet=self._name)
        require(self._client._ready(self._name).tip == before.tip, ErrorCode.SNAPSHOT)
        return Amount.from_rpc(result)

    def new_address(self, address_type: str = "bech32m") -> str:
        require(self._client.config.allow_new_addresses, ErrorCode.PERMISSION)
        require(address_type in ("bech32m", "bech32"), ErrorCode.INPUT)
        self._client._ready(self._name)
        # Empty label: customer identifiers and memos do not enter wallet metadata.
        addr = self._client._transport.call("getnewaddress", ["", address_type], wallet=self._name, mutation=True)
        address_value(addr)
        self._owned(addr)
        return addr

    def _owned(self, address: str) -> None:
        info = self._client._transport.call("getaddressinfo", [address], wallet=self._name)
        require(isinstance(info, dict) and (info.get("ismine") is True or info.get("iswatchonly") is True), ErrorCode.INPUT)

    def create_request(self, amount: Amount, confirmations: int = 6) -> PaymentRequest:
        require(isinstance(amount, Amount) and amount.units > 0, ErrorCode.AMOUNT)
        require(type(confirmations) is int and 1 <= confirmations <= 1000, ErrorCode.INPUT)
        return PaymentRequest(uuid.uuid4().hex, self._client.config.network, self.new_address(), amount, confirmations)

    def send(self, address: str, amount: Amount) -> str:
        """Explicit capability + per-call cap. Never automatically retry this operation."""
        cfg = self._client.config
        require(cfg.send_limit is not None, ErrorCode.PERMISSION)
        require(isinstance(amount, Amount) and 0 < amount.units <= cfg.send_limit.units, ErrorCode.AMOUNT)
        address_value(address)
        self._client._ready(self._name)
        valid = self._client._transport.call("validateaddress", [address])
        require(isinstance(valid, dict) and valid.get("isvalid") is True, ErrorCode.INPUT)
        txid = self._client._transport.call("sendtoaddress", [address, amount], wallet=self._name, mutation=True)
        if not isinstance(txid, str) or HASH.fullmatch(txid) is None:
            raise WamError(ErrorCode.OUTCOME_UNKNOWN)
        return txid

    def observe(self, request: PaymentRequest, known_txids: tuple[str, ...] = ()) -> PaymentReceipt:
        """Re-read authoritative wallet receipts, not just unspent outputs."""
        require(isinstance(request, PaymentRequest) and request.network is self._client.config.network, ErrorCode.NETWORK)
        require(isinstance(known_txids, tuple) and len(known_txids) <= 2000, ErrorCode.INPUT)
        client, rpc = self._client, self._client._transport
        before = client._ready(self._name)
        self._owned(request.address)
        rows = rpc.call("listreceivedbyaddress", [0, False, True, request.address], wallet=self._name)
        require(isinstance(rows, list))
        ids = set(hash_value(txid) for txid in known_txids)
        for row in rows:
            require(isinstance(row, dict))
            if row.get("address") == request.address:
                require(isinstance(row.get("txids"), list))
                ids.update(hash_value(txid) for txid in row["txids"])
        require(len(ids) <= 2000, ErrorCode.SIZE)
        outputs: dict[tuple[str,int], PaymentOutput] = {}
        for txid in sorted(ids):
            tx = rpc.call("gettransaction", [txid, True], wallet=self._name)
            require(isinstance(tx, dict) and tx.get("txid") == txid and type(tx.get("confirmations")) is int)
            require(isinstance(tx.get("lastprocessedblock"), dict) and
                    tx["lastprocessedblock"].get("hash") == before.tip, ErrorCode.SNAPSHOT)
            conf = tx["confirmations"]
            if conf < 0 or tx.get("abandoned") is True or tx.get("generated") is True:
                continue
            if conf == 0:
                try: rpc.call("getmempoolentry", [txid])
                except WamError as exc:
                    if exc.code is ErrorCode.RPC and exc.rpc_code == -5: continue
                    raise
            require(isinstance(tx.get("details"), list))
            for detail in tx["details"]:
                require(isinstance(detail, dict))
                if detail.get("category") != "receive" or detail.get("address") != request.address or detail.get("abandoned"):
                    continue
                vout = detail.get("vout")
                require(type(vout) is int and 0 <= vout < 2**32)
                amount = Amount.from_rpc(detail.get("amount"))
                if amount.units == 0: continue
                output = PaymentOutput(txid, vout, amount, conf)
                key = (txid, vout)
                require(key not in outputs or outputs[key] == output, ErrorCode.SNAPSHOT)
                outputs[key] = output
        require(client._ready(self._name).tip == before.tip, ErrorCode.SNAPSHOT)
        result = PaymentReceipt(request, before.tip, before.blocks, tuple(outputs.values()))
        # Evaluate sums now so malformed/oversized totals cannot appear as a valid receipt.
        result.received
        result.confirmed
        return result
