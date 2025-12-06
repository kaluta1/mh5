"""
Crypto Payment Service - Integration with payment provider
"""

import aiohttp
import hmac
import hashlib
import json
from typing import Optional, Dict, Any, List
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class CryptoPaymentError(Exception):
    """Exception for Crypto Payment API errors"""
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class CryptoPaymentService:
    """Service for crypto payments"""
    
    def __init__(self):
        self.api_key = settings.CRYPTO_PAYMENT_API_KEY
        self.api_url = settings.CRYPTO_PAYMENT_API_URL
        self.ipn_secret = settings.CRYPTO_PAYMENT_IPN_SECRET
        
    @property
    def headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    async def get_status(self) -> Dict[str, Any]:
        """Check API status"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/status", headers=self.headers) as response:
                return await response.json()
    
    async def get_available_currencies(self) -> List[str]:
        """Get list of available cryptocurrencies"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/currencies", headers=self.headers) as response:
                if response.status != 200:
                    raise CryptoPaymentError("Failed to get currencies", response.status)
                data = await response.json()
                return data.get("currencies", [])
    
    async def get_minimum_amount(self, currency_from: str, currency_to: str = "usd") -> float:
        """Get minimum payment amount for a currency"""
        async with aiohttp.ClientSession() as session:
            params = {"currency_from": currency_from, "currency_to": currency_to}
            async with session.get(f"{self.api_url}/min-amount", params=params, headers=self.headers) as response:
                if response.status != 200:
                    raise CryptoPaymentError("Failed to get minimum amount", response.status)
                data = await response.json()
                return data.get("min_amount", 0)
    
    async def get_estimate(self, amount: float, currency_from: str, currency_to: str) -> Dict[str, Any]:
        """Get estimated conversion amount"""
        async with aiohttp.ClientSession() as session:
            params = {"amount": amount, "currency_from": currency_from, "currency_to": currency_to}
            async with session.get(f"{self.api_url}/estimate", params=params, headers=self.headers) as response:
                if response.status != 200:
                    raise CryptoPaymentError("Failed to get estimate", response.status)
                return await response.json()
    
    async def create_payment(
        self,
        price_amount: float,
        price_currency: str = "usd",
        pay_currency: str = "btc",
        order_id: Optional[str] = None,
        order_description: Optional[str] = None,
        ipn_callback_url: Optional[str] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a crypto payment
        
        Returns: {payment_id, pay_address, pay_amount, pay_currency, ...}
        """
        payload = {
            "price_amount": price_amount,
            "price_currency": price_currency,
            "pay_currency": pay_currency,
        }
        
        if order_id:
            payload["order_id"] = order_id
        if order_description:
            payload["order_description"] = order_description
        if ipn_callback_url:
            payload["ipn_callback_url"] = ipn_callback_url
        if success_url:
            payload["success_url"] = success_url
        if cancel_url:
            payload["cancel_url"] = cancel_url
            
        logger.info(f"Creating crypto payment: {price_amount} {price_currency} -> {pay_currency}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_url}/payment", json=payload, headers=self.headers) as response:
                if response.status not in [200, 201]:
                    text = await response.text()
                    logger.error(f"Crypto payment error: {text}")
                    raise CryptoPaymentError(f"Failed to create payment", response.status)
                
                result = await response.json()
                logger.info(f"Payment created: {result.get('payment_id')}")
                return result
    
    async def create_invoice(
        self,
        price_amount: float,
        price_currency: str = "usd",
        order_id: Optional[str] = None,
        order_description: Optional[str] = None,
        ipn_callback_url: Optional[str] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an invoice (hosted payment page where user chooses crypto)
        
        Returns: {id, invoice_url, ...}
        """
        payload = {
            "price_amount": price_amount,
            "price_currency": price_currency,
        }
        
        if order_id:
            payload["order_id"] = order_id
        if order_description:
            payload["order_description"] = order_description
        if ipn_callback_url:
            payload["ipn_callback_url"] = ipn_callback_url
        if success_url:
            payload["success_url"] = success_url
        if cancel_url:
            payload["cancel_url"] = cancel_url
            
        logger.info(f"Creating crypto invoice: {price_amount} {price_currency}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.api_url}/invoice", json=payload, headers=self.headers) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Crypto invoice error: {text}")
                    raise CryptoPaymentError(f"Failed to create invoice", response.status)
                
                result = await response.json()
                logger.info(f"Invoice created: {result.get('id')}")
                return result
    
    async def get_payment_status(self, payment_id: int) -> Dict[str, Any]:
        """Get payment status by ID"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/payment/{payment_id}", headers=self.headers) as response:
                if response.status != 200:
                    raise CryptoPaymentError("Failed to get payment status", response.status)
                return await response.json()
    
    def verify_ipn_signature(self, payload: dict, signature: str) -> bool:
        """Verify IPN webhook signature"""
        if not self.ipn_secret:
            logger.warning("IPN secret not configured, skipping signature verification")
            return True
            
        sorted_payload = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        calculated_signature = hmac.new(
            self.ipn_secret.encode(),
            sorted_payload.encode(),
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(calculated_signature, signature)


# Singleton instance
crypto_payment_service = CryptoPaymentService()
