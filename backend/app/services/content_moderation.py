"""
Service de modération de contenu
Utilise Sightengine pour la modération d'images/vidéos
"""

import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class ContentType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    TEXT = "text"


class FlagType(str, Enum):
    ADULT = "adult"
    VIOLENCE = "violence"
    GORE = "gore"
    WEAPONS = "weapons"
    DRUGS = "drugs"
    HATE = "hate"
    OFFENSIVE = "offensive"
    SPAM = "spam"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ContentFlag:
    type: FlagType
    severity: Severity
    confidence: float
    description: str


@dataclass
class ModerationResult:
    is_approved: bool
    confidence: float
    flags: List[ContentFlag]
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_approved": self.is_approved,
            "confidence": self.confidence,
            "flags": [
                {
                    "type": f.type.value,
                    "severity": f.severity.value,
                    "confidence": f.confidence,
                    "description": f.description
                }
                for f in self.flags
            ],
            "details": self.details
        }


# Seuils de modération
MODERATION_THRESHOLDS = {
    "nudity": 0.6,
    "violence": 0.6,
    "gore": 0.4,
    "weapons": 0.6,
    "offensive": 0.6,
    "drugs": 0.6,
    "tobacco" :0.6,
}

# Liste de mots interdits pour la modération de texte
FORBIDDEN_WORDS = [
    # Insultes et vulgarités (à personnaliser)
    "putain", "merde", "connard", "salope", "enculé", "nul",
    # Anglais
    "fuck", "shit", "bitch", "asshole", "dick", "hate",
    # Spam
    "click here", "free money", "earn fast",
]


class ContentModerationService:
    """Service de modération de contenu"""
    
    def __init__(self):
        self.api_user = getattr(settings, 'SIGHTENGINE_API_USER', None)
        self.api_secret = getattr(settings, 'SIGHTENGINE_API_KEY', None)
        self.enabled = getattr(settings, 'ENABLE_CONTENT_MODERATION', False)
        
    def is_configured(self) -> bool:
        """Vérifie si le service est configuré"""
        return bool(self.api_user and self.api_secret and self.enabled)
    
    def moderate_image(self, image_url: str) -> ModerationResult:
        """Modère une image avec Sightengine"""
        if not self.is_configured():
            logger.info("Content moderation not configured, skipping image moderation")
            return ModerationResult(
                is_approved=True,
                confidence=0,
                flags=[],
                details={"skipped": True, "reason": "not_configured"}
            )
        
        logger.info(f"Moderating image: {image_url[:100]}...")
        
        try:
            response = requests.get(
                "https://api.sightengine.com/1.0/check.json",
                params={
                    "url": image_url,
                    "models": "nudity-2.0,tobacco,violence,gore,weapon,offensive-2.0,scam",
                    "api_user": self.api_user,
                    "api_secret": self.api_secret
                },
                timeout=15  # Réduit de 30 à 15 secondes
            )
            
            if response.status_code != 200:
                logger.error(f"Sightengine API error: {response.status_code} - {response.text[:200]}")
                # En cas d'erreur API, on laisse passer (fail-open)
                return ModerationResult(
                    is_approved=True,
                    confidence=0,
                    flags=[],
                    details={"error": f"API error: {response.status_code}", "fail_open": True}
                )
            
            data = response.json()
            logger.info(f"Image moderation result: approved={data.get('status') == 'success'}")
            return self._process_sightengine_response(data)
                
        except requests.exceptions.Timeout:
            logger.warning(f"Image moderation timeout for: {image_url[:100]}")
            # En cas de timeout, on laisse passer (fail-open)
            return ModerationResult(
                is_approved=True,
                confidence=0,
                flags=[],
                details={"error": "timeout", "fail_open": True}
            )
        except Exception as e:
            logger.error(f"Image moderation error: {type(e).__name__}: {e}")
            # En cas d'erreur, on laisse passer (fail-open)
            return ModerationResult(
                is_approved=True,
                confidence=0,
                flags=[],
                details={"error": str(e), "fail_open": True}
            )
    
    def moderate_video(self, video_url: str) -> ModerationResult:
        """Modère une vidéo avec Sightengine (analyse synchrone)"""
        if not self.is_configured():
            logger.info("Content moderation not configured, skipping video moderation")
            return ModerationResult(
                is_approved=True,
                confidence=0,
                flags=[],
                details={"skipped": True, "reason": "not_configured"}
            )
        
        logger.info(f"Moderating video: {video_url[:100]}...")
        
        try:
            response = requests.post(
                "https://api.sightengine.com/1.0/video/check-sync.json",
                data={
                    "stream_url": video_url,
                    "models": "nudity-2.0,violence,gore,weapon,offensive",
                    "api_user": self.api_user,
                    "api_secret": self.api_secret,
                    "interval": "2.0"
                },
                timeout=30  # Réduit de 60 à 30 secondes
            )
            
            if response.status_code != 200:
                logger.error(f"Sightengine Video API error: {response.status_code} - {response.text[:200]}")
                # En cas d'erreur API, on laisse passer (fail-open)
                return ModerationResult(
                    is_approved=True,
                    confidence=0,
                    flags=[],
                    details={"error": f"API error: {response.status_code}", "fail_open": True}
                )
            
            data = response.json()
            logger.info(f"Video moderation result: approved={data.get('status') == 'success'}")
            return self._process_video_response(data)
        
        except requests.exceptions.Timeout:
            logger.warning(f"Video moderation timeout for: {video_url[:100]}")
            # En cas de timeout, on laisse passer (fail-open)
            return ModerationResult(
                is_approved=True,
                confidence=0,
                flags=[],
                details={"error": "timeout", "fail_open": True}
            )
        except Exception as e:
            logger.error(f"Video moderation error: {type(e).__name__}: {e}")
            # En cas d'erreur, on laisse passer (fail-open)
            return ModerationResult(
                is_approved=True,
                confidence=0,
                flags=[],
                details={"error": str(e), "fail_open": True}
            )
    
    def moderate_text(self, text: str) -> ModerationResult:
        """Modère un texte (commentaires, descriptions)"""
        if not text:
            return ModerationResult(
                is_approved=True,
                confidence=1.0,
                flags=[],
                details={}
            )
        
        flags = []
        text_lower = text.lower()
        
        # Vérifier les mots interdits
        for word in FORBIDDEN_WORDS:
            if word.lower() in text_lower:
                flags.append(ContentFlag(
                    type=FlagType.OFFENSIVE,
                    severity=Severity.MEDIUM,
                    confidence=1.0,
                    description=f"Mot interdit détecté"
                ))
                break
        
        # Vérifier le spam (caractères répétés, caps lock excessif)
        if self._is_spam(text):
            flags.append(ContentFlag(
                type=FlagType.SPAM,
                severity=Severity.LOW,
                confidence=0.8,
                description="Contenu spam détecté"
            ))
        
        is_approved = len(flags) == 0
        max_confidence = max((f.confidence for f in flags), default=1.0)
        
        return ModerationResult(
            is_approved=is_approved,
            confidence=max_confidence,
            flags=flags,
            details={"text_length": len(text)}
        )
    
    def _is_spam(self, text: str) -> bool:
        """Détecte le spam basique"""
        # Trop de majuscules
        if len(text) > 10:
            upper_ratio = sum(1 for c in text if c.isupper()) / len(text)
            if upper_ratio > 0.7:
                return True
        
        # Caractères répétés
        for i in range(len(text) - 4):
            if len(set(text[i:i+5])) == 1:
                return True
        
        return False
    
    def _process_sightengine_response(self, data: Dict[str, Any]) -> ModerationResult:
        """Traite la réponse de Sightengine pour les images"""
        flags = []
        is_approved = True
        
        # Nudité
        if "nudity" in data:
            nudity_score = max(
                data["nudity"].get("sexual_activity", 0),
                data["nudity"].get("sexual_display", 0),
                data["nudity"].get("erotica", 0)
            )
            if nudity_score > MODERATION_THRESHOLDS["nudity"]:
                is_approved = False
                flags.append(ContentFlag(
                    type=FlagType.ADULT,
                    severity=Severity.HIGH if nudity_score > 0.8 else Severity.MEDIUM,
                    confidence=nudity_score,
                    description="Contenu adulte détecté"
                ))
        
        # Violence
        if "violence" in data:
            violence_score = data["violence"].get("prob", 0)
            if violence_score > MODERATION_THRESHOLDS["violence"]:
                is_approved = False
                flags.append(ContentFlag(
                    type=FlagType.VIOLENCE,
                    severity=Severity.HIGH if violence_score > 0.85 else Severity.MEDIUM,
                    confidence=violence_score,
                    description="Contenu violent détecté"
                ))
        
        # Gore
        if "gore" in data:
            gore_score = data["gore"].get("prob", 0)
            if gore_score > MODERATION_THRESHOLDS["gore"]:
                is_approved = False
                flags.append(ContentFlag(
                    type=FlagType.GORE,
                    severity=Severity.HIGH if gore_score > 0.7 else Severity.MEDIUM,
                    confidence=gore_score,
                    description="Contenu gore/sanglant détecté"
                ))
        
        # Armes
        if "weapon" in data:
            weapon_score = data["weapon"].get("prob", 0)
            if weapon_score > MODERATION_THRESHOLDS["weapons"]:
                is_approved = False
                flags.append(ContentFlag(
                    type=FlagType.WEAPONS,
                    severity=Severity.MEDIUM,
                    confidence=weapon_score,
                    description="Arme détectée"
                ))
        
        # Contenu offensant
        if "offensive" in data:
            offensive_score = data["offensive"].get("prob", 0)
            if offensive_score > MODERATION_THRESHOLDS["offensive"]:
                is_approved = False
                flags.append(ContentFlag(
                    type=FlagType.OFFENSIVE,
                    severity=Severity.MEDIUM,
                    confidence=offensive_score,
                    description="Contenu offensant détecté"
                ))
        
        max_confidence = max((f.confidence for f in flags), default=1.0)
        
        return ModerationResult(
            is_approved=is_approved,
            confidence=max_confidence,
            flags=flags,
            details={
                "nudity": data.get("nudity"),
                "violence": data.get("violence"),
                "gore": data.get("gore"),
                "weapon": data.get("weapon"),
                "offensive": data.get("offensive")
            }
        )
    
    def _process_video_response(self, data: Dict[str, Any]) -> ModerationResult:
        """Traite la réponse de modération vidéo"""
        flags = []
        is_approved = True
        max_confidence = 0
        
        # Parcourir les frames analysées
        frames = data.get("frames", [])
        for frame in frames:
            frame_result = self._process_sightengine_response(frame)
            if not frame_result.is_approved:
                is_approved = False
                for flag in frame_result.flags:
                    # Éviter les doublons
                    existing = next((f for f in flags if f.type == flag.type), None)
                    if not existing or existing.confidence < flag.confidence:
                        flags = [f for f in flags if f.type != flag.type]
                        flags.append(flag)
                    max_confidence = max(max_confidence, flag.confidence)
        
        return ModerationResult(
            is_approved=is_approved,
            confidence=max_confidence if flags else 1.0,
            flags=flags,
            details={"frames_analyzed": len(frames)}
        )
    
    def moderate_content(
        self,
        content_type: ContentType,
        url: Optional[str] = None,
        text: Optional[str] = None
    ) -> ModerationResult:
        """Modère le contenu selon son type"""
        if content_type == ContentType.IMAGE and url:
            return self.moderate_image(url)
        elif content_type == ContentType.VIDEO and url:
            return self.moderate_video(url)
        elif content_type == ContentType.TEXT and text:
            return self.moderate_text(text)
        else:
            return ModerationResult(
                is_approved=True,
                confidence=0,
                flags=[],
                details={"error": "Invalid content type or missing content"}
            )


# Instance globale du service
content_moderation_service = ContentModerationService()
