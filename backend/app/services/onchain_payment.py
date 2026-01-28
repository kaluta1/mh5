"""
On-chain payment service (BSC)
Validates contract payments using transaction receipts and events.
"""
from dataclasses import dataclass
from decimal import Decimal
import uuid
from typing import Any, Dict

import requests

from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


@dataclass
class OnchainPaymentDetails:
    payer: str
    amount_wei: int
    token_address: str


class OnchainPaymentError(Exception):
    pass


class OnchainPaymentService:
    def __init__(self) -> None:
        self.chain_id = settings.BSC_CHAIN_ID
        self.contract_address = settings.BSC_PAYMENT_CONTRACT

    def build_order_id(self) -> str:
        """
        Build a bytes32 order id hex string (0x + 64 hex chars).
        """
        raw_hex = uuid.uuid4().hex  # 32 hex chars
        return f"0x{raw_hex.ljust(64, '0')}"

    def to_wei(self, amount: float, decimals: int) -> int:
        return int(Decimal(str(amount)) * (10 ** decimals))

    def _require_contract(self) -> str:
        if not self.contract_address:
            raise OnchainPaymentError("BSC_PAYMENT_CONTRACT not configured")
        return self._normalize_address(self.contract_address)

    def _rpc(self, method: str, params: list) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        try:
            response = requests.post(settings.BSC_RPC_URL, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise OnchainPaymentError(f"BSC RPC error: {e}") from e
        if "error" in data:
            raise OnchainPaymentError(str(data["error"]))
        return data.get("result")

    def _normalize_address(self, address: str) -> str:
        if not address:
            return "0x0000000000000000000000000000000000000000"
        normalized = address.lower()
        if normalized.startswith("0x"):
            normalized = normalized[2:]
        normalized = normalized.rjust(40, "0")[-40:]
        return f"0x{normalized}"

    def _topic_to_address(self, topic: str) -> str:
        if not topic:
            return self._normalize_address("")
        topic_hex = topic.lower()
        if topic_hex.startswith("0x"):
            topic_hex = topic_hex[2:]
        return self._normalize_address(topic_hex[-40:])

    def _hex_to_int(self, value: str) -> int:
        if not value:
            return 0
        return int(value, 16)

    def verify_payment(
        self,
        order_id: str,
        tx_hash: str,
        expected_amount_wei: int,
        token_address: str,
    ) -> OnchainPaymentDetails:
        contract_address = self._require_contract()

        receipt = self._rpc("eth_getTransactionReceipt", [tx_hash])
        if not receipt:
            raise OnchainPaymentError("Transaction not found")

        status_hex = receipt.get("status")
        status = self._hex_to_int(status_hex) if isinstance(status_hex, str) else status_hex
        if status != 1:
            raise OnchainPaymentError("Transaction not confirmed")

        if settings.BSC_CONFIRMATIONS > 1:
            latest_block = self._hex_to_int(self._rpc("eth_blockNumber", []))
            block_number = self._hex_to_int(receipt.get("blockNumber", "0x0"))
            confirmations = latest_block - block_number + 1
            if confirmations < settings.BSC_CONFIRMATIONS:
                raise OnchainPaymentError("Not enough confirmations")

        logs = receipt.get("logs") or []
        for log in logs:
            log_address = self._normalize_address(log.get("address", ""))
            if log_address != contract_address:
                continue

            topics = log.get("topics") or []
            if len(topics) < 3:
                continue

            event_order_id = topics[1].lower()
            if event_order_id != order_id.lower():
                continue

            data = (log.get("data") or "0x")[2:]
            if len(data) < 128:
                continue

            amount_wei = self._hex_to_int(data[:64])
            token = self._normalize_address(data[64:128])
            if self._normalize_address(token_address) != token:
                raise OnchainPaymentError("Token mismatch")
            if amount_wei < expected_amount_wei:
                raise OnchainPaymentError("Amount below expected")

            payer = self._topic_to_address(topics[2])
            return OnchainPaymentDetails(
                payer=payer,
                amount_wei=amount_wei,
                token_address=token,
            )

        raise OnchainPaymentError("Payment event not found in transaction")


onchain_payment_service = OnchainPaymentService()
