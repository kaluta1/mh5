"""
Service pour extraire les informations de l'appareil et de la localisation depuis une requête HTTP
"""
from typing import Dict, Any, Optional
from fastapi import Request
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> Optional[str]:
    """
    Récupère l'adresse IP réelle du client depuis la requête.
    Prend en compte les proxies et load balancers.
    """
    # Vérifier d'abord les headers de proxy courants
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For peut contenir plusieurs IPs, prendre la première
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            return ip
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fallback sur l'IP directe du client
    if request.client:
        return request.client.host
    
    return None


def get_user_agent(request: Request) -> Optional[str]:
    """Récupère le User-Agent depuis les headers"""
    return request.headers.get("User-Agent")


def get_device_info(request: Request) -> Dict[str, Any]:
    """
    Extrait les informations de l'appareil depuis la requête HTTP.
    """
    user_agent = get_user_agent(request)
    
    device_info: Dict[str, Any] = {
        "user_agent": user_agent
    }
    
    if user_agent:
        # Parser le User-Agent pour extraire des informations
        user_agent_lower = user_agent.lower()
        
        # Détecter le système d'exploitation
        if "windows" in user_agent_lower:
            device_info["platform"] = "Windows"
            if "windows nt 10.0" in user_agent_lower:
                device_info["os_version"] = "Windows 10/11"
            elif "windows nt 6.3" in user_agent_lower:
                device_info["os_version"] = "Windows 8.1"
            elif "windows nt 6.2" in user_agent_lower:
                device_info["os_version"] = "Windows 8"
            elif "windows nt 6.1" in user_agent_lower:
                device_info["os_version"] = "Windows 7"
        elif "mac" in user_agent_lower or "darwin" in user_agent_lower:
            device_info["platform"] = "macOS"
        elif "linux" in user_agent_lower:
            device_info["platform"] = "Linux"
        elif "android" in user_agent_lower:
            device_info["platform"] = "Android"
        elif "iphone" in user_agent_lower or "ipad" in user_agent_lower or "ipod" in user_agent_lower:
            device_info["platform"] = "iOS"
        else:
            device_info["platform"] = "Unknown"
        
        # Détecter le navigateur
        if "chrome" in user_agent_lower and "edg" not in user_agent_lower:
            device_info["browser"] = "Chrome"
        elif "firefox" in user_agent_lower:
            device_info["browser"] = "Firefox"
        elif "safari" in user_agent_lower and "chrome" not in user_agent_lower:
            device_info["browser"] = "Safari"
        elif "edg" in user_agent_lower:
            device_info["browser"] = "Edge"
        elif "opera" in user_agent_lower or "opr" in user_agent_lower:
            device_info["browser"] = "Opera"
        else:
            device_info["browser"] = "Unknown"
        
        # Détecter si c'est un appareil mobile
        mobile_keywords = ["mobile", "android", "iphone", "ipad", "ipod", "blackberry", "windows phone"]
        device_info["is_mobile"] = any(keyword in user_agent_lower for keyword in mobile_keywords)
    
    # Informations supplémentaires depuis les headers
    accept_language = request.headers.get("Accept-Language")
    if accept_language:
        device_info["accept_language"] = accept_language
    
    accept_encoding = request.headers.get("Accept-Encoding")
    if accept_encoding:
        device_info["accept_encoding"] = accept_encoding
    
    return device_info


async def get_location_info(request: Request, ip_address: Optional[str] = None) -> Dict[str, Any]:
    """
    Récupère les informations de localisation basées sur l'adresse IP.
    Utilise une API externe pour géolocaliser l'IP.
    Structure identique à celle utilisée dans la newsletter : ip, city, timezone, continent
    
    Même logique que le frontend : appelle https://ipapi.co/json/ pour obtenir toutes les infos
    """
    location_info: Dict[str, Any] = {}
    
    # Récupérer l'IP réelle du client (comme dans le frontend)
    if not ip_address:
        ip_address = get_client_ip(request)
    
    # Utiliser une API de géolocalisation gratuite (même que le frontend)
    try:
        import httpx
        
        # Utiliser ipapi.co/json/ comme dans le frontend pour obtenir toutes les infos
        # Si on a une IP, on l'utilise, sinon l'API détecte automatiquement
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                # Appeler l'API comme dans le frontend
                if ip_address and ip_address not in ["127.0.0.1", "localhost", "::1"] and not ip_address.startswith("192.168.") and not ip_address.startswith("10.") and not ip_address.startswith("172."):
                    # Pour les IPs publiques, utiliser l'IP spécifique
                    url = f"https://ipapi.co/{ip_address}/json/"
                else:
                    # Pour les IPs locales ou si pas d'IP, laisser l'API détecter
                    # Mais côté serveur, on doit passer l'IP extraite de la requête
                    # On utilise quand même l'IP extraite si disponible
                    if ip_address:
                        url = f"https://ipapi.co/{ip_address}/json/"
                    else:
                        # Si vraiment pas d'IP, on ne peut pas faire la requête
                        return location_info
                
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    
                    if "error" not in data:
                        # Structure identique à la newsletter : ip, city, timezone, continent
                        # Utiliser les mêmes noms de champs que le frontend
                        # L'API retourne l'IP dans le champ "ip", utiliser celle-ci (plus fiable)
                        location_info["ip"] = data.get("ip") or ip_address  # IP retournée par l'API (plus fiable) ou celle extraite en fallback
                        location_info["city"] = data.get("city")
                        location_info["timezone"] = data.get("timezone")
                        location_info["continent"] = data.get("continent_code")  # continent_code comme dans le frontend
                        # Optionnel : country pour plus d'infos (country_name comme dans le frontend)
                        location_info["country"] = data.get("country_name")
                        return location_info
            except Exception as e:
                logger.warning(f"Erreur avec ipapi.co: {e}")
            
            # Fallback: essayer ip-api.com (gratuit, 45 requêtes/minute)
            try:
                if ip_address and ip_address not in ["127.0.0.1", "localhost", "::1"] and not ip_address.startswith("192.168.") and not ip_address.startswith("10.") and not ip_address.startswith("172."):
                    url = f"http://ip-api.com/json/{ip_address}"
                else:
                    if ip_address:
                        url = f"http://ip-api.com/json/{ip_address}"
                    else:
                        return location_info
                
                response = await client.get(url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "success":
                        # Structure identique à la newsletter : ip, city, timezone, continent
                        location_info["ip"] = data.get("query") or ip_address  # ip-api.com utilise "query" pour l'IP
                        location_info["city"] = data.get("city")
                        location_info["timezone"] = data.get("timezone")
                        # ip-api.com ne fournit pas le continent, on laisse None
                        location_info["continent"] = None
                        # Optionnel : country pour plus d'infos
                        location_info["country"] = data.get("country")
                        return location_info
            except Exception as e:
                logger.warning(f"Erreur avec ip-api.com: {e}")
    
    except ImportError:
        logger.warning("httpx n'est pas installé, impossible de récupérer la géolocalisation")
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la géolocalisation: {e}")
    
    # Si on n'a pas pu récupérer les infos, on retourne au moins l'IP extraite
    if ip_address:
        location_info["ip"] = ip_address
    
    return location_info


def extract_login_info(request: Request) -> Dict[str, Any]:
    """
    Extrait toutes les informations nécessaires pour un log de connexion depuis la requête.
    Version synchrone pour les cas où on ne peut pas utiliser async.
    """
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)
    device_info = get_device_info(request)
    
    return {
        "ip_address": ip_address,
        "user_agent": user_agent,
        "device_info": device_info
    }

