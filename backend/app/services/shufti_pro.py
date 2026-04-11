"""
Service d'intégration Shufti Pro pour la vérification KYC
Documentation: https://api.shuftipro.com/docs/
"""
import aiohttp
import base64
import json
import hashlib
import hmac
import logging
import random
import string
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

# URLs Shufti Pro
SHUFTI_BASE_URL = "https://api.shuftipro.com"


def _shufti_leaf_pass(val: Any) -> Optional[bool]:
    """
    Interpret a Shufti verification_result leaf value.
    Returns True/False when known, None when absent or inconclusive (caller may fall back to overall event).
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if val == 1:
            return True
        if val == 0:
            return False
        return None
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ("1", "true", "yes", "clear", "verified", "accepted", "pass", "passed"):
            return True
        if s in ("0", "false", "no", "declined", "rejected", "fail", "failed"):
            return False
        return None
    if isinstance(val, dict):
        if not val:
            return None
        any_fail = False
        any_pass = False
        for sub in val.values():
            st = _shufti_leaf_pass(sub)
            if st is None:
                continue
            if st is False:
                any_fail = True
            else:
                any_pass = True
        if any_fail:
            return False
        if any_pass:
            return True
        return None
    if isinstance(val, list):
        if not val:
            return None
        any_fail = False
        any_pass = False
        for item in val:
            st = _shufti_leaf_pass(item)
            if st is None:
                continue
            if st is False:
                any_fail = True
            else:
                any_pass = True
        if any_fail:
            return False
        if any_pass:
            return True
        return None
    return None


def _shufti_service_pass(service_val: Any, overall_fallback: bool) -> bool:
    agg = _shufti_leaf_pass(service_val)
    if agg is None:
        return overall_fallback
    return agg


def kyc_flags_from_shufti_payload(payload: Dict[str, Any], *, overall_accepted: bool) -> Dict[str, bool]:
    """
    Map Shufti status/webhook JSON to our four booleans.
    identity_verified follows document (ID was verified).
    Missing service keys in verification_result fall back to overall_accepted.
    """
    vr = payload.get("verification_result")
    if not isinstance(vr, dict):
        v = overall_accepted
        return {
            "identity_verified": v,
            "document_verified": v,
            "face_verified": v,
            "address_verified": v,
        }
    doc = _shufti_service_pass(vr.get("document"), overall_accepted)
    face = _shufti_service_pass(vr.get("face"), overall_accepted)
    addr_raw = vr.get("address")
    if addr_raw is None:
        addr_raw = vr.get("proof_of_address")
    if addr_raw is None:
        addr_raw = vr.get("address_proof")
    addr = _shufti_service_pass(addr_raw, overall_accepted)
    return {
        "identity_verified": doc,
        "document_verified": doc,
        "face_verified": face,
        "address_verified": addr,
    }

# Configuration
SHUFTI_RETENTION_DAYS = 5  # Nombre de jours de rétention d'une vérification
SHUFTI_TTL_MINUTES = (SHUFTI_RETENTION_DAYS + 1) * 24 * 60  # TTL en minutes


def resolve_shufti_callback_and_redirect_urls() -> Tuple[str, str]:
    """
    Shufti requires allowlisted domains for callback_url and redirect_url.
    Explicit SHUFTI_* env wins; otherwise derive from BACKEND_PUBLIC_URL (same host as API).
    """
    api_v1 = settings.API_V1_STR.rstrip("/")
    base = (settings.BACKEND_PUBLIC_URL or "").strip().rstrip("/")

    callback = (settings.SHUFTI_CALLBACK_URL or "").strip()
    if not callback and base:
        callback = f"{base}{api_v1}/kyc/webhook/shufti-pro"

    redirect = (settings.SHUFTI_REDIRECT_URL or "").strip()
    if not redirect and base:
        redirect = f"{base}{api_v1}/kyc/redirect"

    return callback, redirect


def normalize_country_iso2_for_shufti(country: Optional[str]) -> Optional[str]:
    """
    Shufti expects ISO 3166-1 alpha-2 (exactly 2 letters). Profile often stores full names.
    Only pass through values that are already valid 2-letter codes; otherwise omit.
    """
    if not country or not str(country).strip():
        return None
    c = str(country).strip().upper()
    if len(c) == 2 and c.isalpha():
        return c
    return None


class ShuftiProService:
    """Service pour interagir avec l'API Shufti Pro"""
    
    def __init__(self):
        self.client_id = settings.SHUFTI_CLIENT_ID
        self.secret_key = settings.SHUFTI_SECRET_KEY
        self.callback_url, self.redirect_url = resolve_shufti_callback_and_redirect_urls()
        self.frontend_url = settings.FRONTEND_URL
    
    def _get_auth_header(self) -> str:
        """Générer le header d'authentification Basic"""
        credentials = f"{self.client_id}:{self.secret_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    def _generate_signature(self, payload: str) -> str:
        """Générer la signature HMAC pour la requête"""
        return hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
    
    @staticmethod
    def generate_reference() -> str:
        """
        Générer une référence unique aléatoire (comme dans le code PHP)
        """
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(16))
    
    async def check_reference_validity(self, reference: str) -> Dict[str, Any]:
        """
        Vérifier si une référence existante est toujours valide
        
        Args:
            reference: Identifiant de la vérification existante
        
        Returns:
            Dict avec is_valid, event, et les données
        """
        payload = {
            "reference": reference
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{SHUFTI_BASE_URL}/status",
                    json=payload,
                    headers={
                        "Authorization": self._get_auth_header(),
                        "Content-Type": "application/json"
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    
                    event = result.get("event", "")
                    
                    # request.invalid signifie que la référence n'est plus valide
                    if event == "request.invalid":
                        return {
                            "is_valid": False,
                            "event": event,
                            "data": result
                        }
                    
                    # verification.accepted ou verification.declined = terminé
                    if event in ["verification.accepted", "verification.declined"]:
                        return {
                            "is_valid": False,  # Terminé, doit créer une nouvelle
                            "is_completed": True,
                            "is_accepted": event == "verification.accepted",
                            "event": event,
                            "data": result
                        }
                    
                    # Encore en cours (request.pending, verification.pending, etc.)
                    return {
                        "is_valid": True,
                        "event": event,
                        "verification_url": result.get("verification_url"),
                        "data": result
                    }
                    
        except Exception as e:
            logger.error(f"Shufti Pro reference check failed: {e}")
            return {
                "is_valid": False,
                "error": str(e)
            }
    
    async def initiate_verification(
        self,
        reference: str,
        email: str,
        country: Optional[str] = None,
        language: str = "FR",
        redirect_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initier une vérification KYC avec Shufti Pro (document + face uniquement).

        Le justificatif de domicile est géré hors Shufti (plan / flux interne).

        Args:
            reference: Identifiant unique pour cette vérification
            email: Email de l'utilisateur
            country: Code pays ISO (optionnel, pour pré-remplir)
            language: Langue de l'interface (FR, EN, ES, etc.)
            redirect_url: URL de redirection après vérification

        Returns:
            Dict contenant verification_url et autres données
        """
        # Redirect after verification: explicit arg > env-derived (see resolve_shufti_callback_and_redirect_urls)
        # Domains must be allowlisted in the Shufti Pro dashboard (callback + redirect).
        if not redirect_url:
            redirect_url = self.redirect_url or ""
        
        # Payload pour la vérification (basé sur le code PHP fonctionnel).
        # Ne pas envoyer de chaînes vides pour name/dob/etc. : Shufti renvoie souvent
        # event "request.invalid" (écran INVALID dans l'iframe) si le format est incohérent.
        payload: Dict[str, Any] = {
            "reference": reference,
            "callback_url": self.callback_url,
            "redirect_url": redirect_url,
            "email": email,
            "language": language,
            "verification_mode": "any",
            "allow_offline": "1",
            "allow_online": "1",
            "show_privacy_policy": "1",
            "show_results": "1",
            "show_consent": "1",
            "show_feedback_form": "0",
            "ttl": SHUFTI_TTL_MINUTES,  # 6 jours en minutes
            "face": {
                "proof": ""
            },
            "document": {
                "supported_types": ["id_card", "passport", "driving_license"],
                "fetch_enhanced_data": "0",
                "allow_offline": "1",
                "allow_online": "1",
                "verification_instructions": {
                    "allow_paper_based": "1",
                    "allow_screenshot": "1",
                    "allow_cropped": "1",
                    "allow_scanned": "1",
                    "allow_e_document": "1"
                }
            },
        }
        iso2 = normalize_country_iso2_for_shufti(country)
        if iso2:
            payload["country"] = iso2

        if not (self.client_id or "").strip() or not (self.secret_key or "").strip():
            logger.error("Shufti Pro: SHUFTI_CLIENT_ID or SHUFTI_SECRET_KEY is empty — check backend .env")
            return {
                "success": False,
                "error": (
                    "Shufti Pro is not configured on the server. "
                    "Set SHUFTI_CLIENT_ID and SHUFTI_SECRET_KEY in backend/.env (not the frontend). "
                    "Get keys from the Shufti Pro dashboard."
                ),
                "data": {},
            }

        if not (self.callback_url or "").strip():
            logger.error("Shufti Pro: callback URL empty — set SHUFTI_CALLBACK_URL or BACKEND_PUBLIC_URL in backend .env")
            return {
                "success": False,
                "error": (
                    "Shufti callback URL is not configured. Set SHUFTI_CALLBACK_URL to your public API webhook "
                    f"(e.g. https://your-domain{settings.API_V1_STR}/kyc/webhook/shufti-pro) or set BACKEND_PUBLIC_URL "
                    "to your API base URL so it can be derived automatically. Register that domain in Shufti Backoffice."
                ),
                "data": {},
            }

        if not (redirect_url or "").strip():
            logger.error("Shufti Pro: redirect URL empty — set SHUFTI_REDIRECT_URL or BACKEND_PUBLIC_URL")
            return {
                "success": False,
                "error": (
                    "Shufti redirect URL is not configured. Set SHUFTI_REDIRECT_URL or BACKEND_PUBLIC_URL "
                    f"(redirect is derived as BACKEND_PUBLIC_URL + {settings.API_V1_STR}/kyc/redirect). "
                    "Register that domain in Shufti Backoffice."
                ),
                "data": {},
            }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{SHUFTI_BASE_URL}/",
                    json=payload,
                    headers={
                        "Authorization": self._get_auth_header(),
                        "Content-Type": "application/json"
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        event = result.get("event", "")
                        if event == "request.invalid":
                            err = result.get("error") or {}
                            msg = err.get("message", "Invalid request payload") if isinstance(err, dict) else str(err)
                            svc = err.get("service", "") if isinstance(err, dict) else ""
                            key = err.get("key", "") if isinstance(err, dict) else ""
                            hint = f" ({svc}/{key})" if svc or key else ""
                            logger.error("Shufti Pro request.invalid for %s: %s", reference, result)
                            return {
                                "success": False,
                                "error": f"{msg}{hint}",
                                "data": result,
                            }
                        url = result.get("verification_url")
                        if not url:
                            logger.error("Shufti Pro 200 but no verification_url: %s", result)
                            return {
                                "success": False,
                                "error": "Shufti did not return a verification URL",
                                "data": result,
                            }
                        logger.info(f"Shufti Pro verification initiated: {reference}")
                        return {
                            "success": True,
                            "verification_url": url,
                            "reference": reference,
                            "event": event,
                            "data": result
                        }
                    else:
                        logger.error(f"Shufti Pro error: {result}")
                        err_raw = result.get("error")
                        if isinstance(err_raw, dict):
                            msg = err_raw.get("message", "Unknown error")
                        elif isinstance(err_raw, str):
                            msg = err_raw
                        else:
                            msg = "Unknown error"
                        if msg and "authorization keys" in msg.lower():
                            msg = (
                                f"{msg} "
                                "Verify SHUFTI_CLIENT_ID and SHUFTI_SECRET_KEY in backend .env match your Shufti "
                                "dashboard (sandbox vs production). Frontend env vars are not used for API calls."
                            )
                        return {
                            "success": False,
                            "error": msg,
                            "data": result
                        }
                    
        except Exception as e:
            logger.error(f"Shufti Pro request failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_verification_status(self, reference: str) -> Dict[str, Any]:
        """
        Récupérer le statut d'une vérification
        
        Args:
            reference: Identifiant de la vérification
        
        Returns:
            Dict avec le statut et les détails
        """
        payload = {
            "reference": reference
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{SHUFTI_BASE_URL}/status",
                    json=payload,
                    headers={
                        "Authorization": self._get_auth_header(),
                        "Content-Type": "application/json"
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        return {
                            "success": True,
                            "event": result.get("event"),
                            "verification_result": result.get("verification_result"),
                            "data": result
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.get("error", {}).get("message", "Unknown error"),
                            "data": result
                        }
                    
        except Exception as e:
            logger.error(f"Shufti Pro status check failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """
        Vérifier la signature d'un webhook Shufti Pro
        
        Args:
            payload: Corps de la requête webhook
            signature: Signature fournie dans le header
        
        Returns:
            bool: True si la signature est valide
        """
        expected_signature = self._generate_signature(payload)
        return hmac.compare_digest(expected_signature, signature)
    
    def parse_webhook_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parser les données d'un webhook Shufti Pro
        
        Args:
            data: Données du webhook
        
        Returns:
            Dict avec les informations extraites
        """
        event = data.get("event", "")
        reference = data.get("reference", "")
        
        result = {
            "event": event,
            "reference": reference,
            "is_accepted": event == "verification.accepted",
            "is_declined": event == "verification.declined",
            "declined_reason": data.get("declined_reason"),
            "verification_data": data.get("verification_data", {}),
            "proofs": data.get("proofs", {})
        }
        
        # Extraire les données de vérification
        if "verification_data" in data:
            vd = data["verification_data"]
            
            # Document data
            if "document" in vd:
                doc = vd["document"]
                result["document"] = {
                    "first_name": doc.get("name", {}).get("first_name"),
                    "last_name": doc.get("name", {}).get("last_name"),
                    "dob": doc.get("dob"),
                    "document_number": doc.get("document_number"),
                    "document_type": doc.get("document_type"),
                    "issue_date": doc.get("issue_date"),
                    "expiry_date": doc.get("expiry_date"),
                    "country": doc.get("country")
                }
            
            # Address data
            if "address" in vd:
                addr = vd["address"]
                result["address"] = {
                    "full_address": addr.get("full_address"),
                    "country": addr.get("country")
                }
            
            # Face match
            if "face" in vd:
                result["face_match"] = vd["face"].get("match_percentage", 0)
        
        return result


# Instance singleton
shufti_pro_service = ShuftiProService()
