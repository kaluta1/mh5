"""
Service de vérification de la pertinence du contenu
Vérifie si la candidature est en lien avec le concours
"""

import re
import requests
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class RelevanceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class RelevanceResult:
    is_relevant: bool
    score: float  # 0.0 à 1.0
    level: RelevanceLevel
    reasons: List[str]
    suggestions: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_relevant": self.is_relevant,
            "score": self.score,
            "level": self.level.value,
            "reasons": self.reasons,
            "suggestions": self.suggestions
        }


# Seuil minimum de pertinence pour approuver automatiquement
RELEVANCE_THRESHOLD = 0.3  # 30% de pertinence minimum

# Mots-clés par type de concours
CONTEST_TYPE_KEYWORDS = {
    "beauty": {
        "fr": ["beauté", "belle", "beau", "maquillage", "mode", "fashion", "style", "élégance", 
               "charme", "grâce", "visage", "cheveux", "look", "tendance", "glamour", "mannequin",
               "photogénique", "séduisant", "sourire", "yeux", "peau", "silhouette"],
        "en": ["beauty", "beautiful", "gorgeous", "makeup", "fashion", "style", "elegance",
               "charm", "grace", "face", "hair", "look", "trend", "glamour", "model",
               "photogenic", "attractive", "smile", "eyes", "skin", "figure"]
    },
    "talent": {
        "fr": ["talent", "compétence", "art", "musique", "danse", "chant", "performance",
               "créativité", "passion", "spectacle", "artiste", "instrument", "voix",
               "scène", "représentation", "show", "acrobatie", "magie"],
        "en": ["talent", "skill", "art", "music", "dance", "singing", "performance",
               "creativity", "passion", "show", "artist", "instrument", "voice",
               "stage", "act", "acrobatics", "magic"]
    },
    "photography": {
        "fr": ["photo", "photographie", "image", "cliché", "prise de vue", "objectif",
               "lumière", "cadrage", "composition", "portrait", "paysage", "couleur",
               "noir et blanc", "artistique", "créatif"],
        "en": ["photo", "photography", "image", "shot", "lens", "light", "framing",
               "composition", "portrait", "landscape", "color", "black and white",
               "artistic", "creative"]
    },
    "fitness": {
        "fr": ["fitness", "sport", "musculature", "corps", "santé", "entraînement",
               "musculation", "cardio", "forme", "athlète", "performance", "force",
               "endurance", "nutrition", "bien-être"],
        "en": ["fitness", "sport", "body", "health", "training", "workout", "cardio",
               "shape", "athlete", "performance", "strength", "endurance", "nutrition",
               "wellness", "gym"]
    },
    "cooking": {
        "fr": ["cuisine", "recette", "plat", "ingrédient", "chef", "gastronomie",
               "saveur", "goût", "cuisson", "présentation", "restaurant", "menu",
               "délicieux", "gourmand"],
        "en": ["cooking", "recipe", "dish", "ingredient", "chef", "gastronomy",
               "flavor", "taste", "presentation", "restaurant", "menu", "delicious",
               "gourmet", "food"]
    },
    "art": {
        "fr": ["art", "peinture", "dessin", "sculpture", "création", "œuvre",
               "artiste", "couleur", "technique", "style", "expression", "galerie",
               "exposition", "créatif"],
        "en": ["art", "painting", "drawing", "sculpture", "creation", "artwork",
               "artist", "color", "technique", "style", "expression", "gallery",
               "exhibition", "creative"]
    },
    "pet": {
        "fr": ["animal", "chien", "chat", "mignon", "adorable", "compagnon", "race",
               "pelage", "yeux", "joueur", "fidèle", "affectueux", "drôle"],
        "en": ["pet", "dog", "cat", "cute", "adorable", "companion", "breed",
               "fur", "eyes", "playful", "loyal", "affectionate", "funny"]
    },
    "default": {
        "fr": ["concours", "participation", "candidature", "présentation", "motivation",
               "passion", "objectif", "rêve", "ambition", "talent", "unique"],
        "en": ["contest", "participation", "application", "presentation", "motivation",
               "passion", "goal", "dream", "ambition", "talent", "unique"]
    }
}


class ContentRelevanceService:
    """Service de vérification de la pertinence du contenu"""
    
    def __init__(self):
        self.openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        self.use_ai = bool(self.openai_api_key)
    
    def check_relevance(
        self,
        contestant_title: str,
        contestant_description: str,
        contest_title: str,
        contest_description: Optional[str] = None,
        contest_type: Optional[str] = None,
        contest_category: Optional[str] = None
    ) -> RelevanceResult:
        """
        Vérifie si la candidature est pertinente par rapport au concours
        """
        reasons = []
        suggestions = []
        score = 0.0
        
        # Nettoyer les textes
        contestant_text = f"{contestant_title} {contestant_description}".lower()
        contest_text = f"{contest_title} {contest_description or ''}".lower()
        
        # 1. Vérifier la longueur minimale
        if len(contestant_title.strip()) < 5:
            suggestions.append("Le titre est trop court. Ajoutez plus de détails.")
            score -= 0.1
        else:
            score += 0.1
            
        if len(contestant_description.strip()) < 20:
            suggestions.append("La description est trop courte. Expliquez davantage votre candidature.")
            score -= 0.1
        else:
            score += 0.15
        
        # 2. Vérifier les mots-clés du type de concours
        keywords_found = self._check_contest_type_keywords(
            contestant_text, 
            contest_type or "default"
        )
        if keywords_found:
            reasons.append(f"Mots-clés pertinents trouvés: {', '.join(keywords_found[:5])}")
            score += min(0.3, len(keywords_found) * 0.05)
        else:
            suggestions.append("Ajoutez des mots-clés liés au thème du concours.")
        
        # 3. Vérifier le chevauchement de mots avec le titre/description du concours
        overlap_score = self._calculate_text_overlap(contestant_text, contest_text)
        if overlap_score > 0.1:
            reasons.append("Votre texte mentionne des éléments du concours.")
            score += overlap_score * 0.3
        
        # 4. Vérifier que ce n'est pas du contenu générique/spam
        if self._is_generic_content(contestant_text):
            suggestions.append("Votre candidature semble trop générique. Personnalisez-la.")
            score -= 0.2
        else:
            score += 0.1
        
        # 5. Vérifier la présence de liens/URLs suspects
        if self._contains_suspicious_links(contestant_text):
            suggestions.append("Évitez les liens externes dans votre description.")
            score -= 0.15
        
        # 6. Vérifier la cohérence globale
        coherence_score = self._check_coherence(
            contestant_title, 
            contestant_description
        )
        score += coherence_score * 0.15
        if coherence_score > 0.5:
            reasons.append("Le titre et la description sont cohérents.")
        
        # Normaliser le score entre 0 et 1
        score = max(0.0, min(1.0, score))
        
        # Déterminer le niveau de pertinence
        if score >= 0.7:
            level = RelevanceLevel.HIGH
        elif score >= 0.4:
            level = RelevanceLevel.MEDIUM
        elif score >= 0.2:
            level = RelevanceLevel.LOW
        else:
            level = RelevanceLevel.NONE
        
        # Décision finale
        is_relevant = score >= RELEVANCE_THRESHOLD
        
        if not is_relevant:
            suggestions.append(
                "Votre candidature ne semble pas assez liée au concours. "
                "Assurez-vous que votre titre et description correspondent au thème."
            )
        
        return RelevanceResult(
            is_relevant=is_relevant,
            score=score,
            level=level,
            reasons=reasons if reasons else ["Aucune correspondance forte trouvée."],
            suggestions=suggestions
        )
    
    def _check_contest_type_keywords(
        self, 
        text: str, 
        contest_type: str
    ) -> List[str]:
        """Vérifie la présence de mots-clés liés au type de concours"""
        keywords_found = []
        
        # Récupérer les mots-clés pour ce type
        type_key = contest_type.lower() if contest_type else "default"
        keywords_dict = CONTEST_TYPE_KEYWORDS.get(type_key, CONTEST_TYPE_KEYWORDS["default"])
        
        # Chercher dans toutes les langues
        all_keywords = keywords_dict.get("fr", []) + keywords_dict.get("en", [])
        
        for keyword in all_keywords:
            if keyword.lower() in text:
                keywords_found.append(keyword)
        
        return keywords_found
    
    def _calculate_text_overlap(self, text1: str, text2: str) -> float:
        """Calcule le chevauchement entre deux textes"""
        # Tokeniser les textes
        words1 = set(re.findall(r'\b\w{3,}\b', text1.lower()))
        words2 = set(re.findall(r'\b\w{3,}\b', text2.lower()))
        
        # Exclure les mots communs
        common_words = {"les", "des", "une", "pour", "avec", "dans", "sur", "par",
                       "the", "and", "for", "with", "this", "that", "from", "are"}
        words1 = words1 - common_words
        words2 = words2 - common_words
        
        if not words1 or not words2:
            return 0.0
        
        # Calculer l'intersection
        intersection = words1 & words2
        
        # Score basé sur l'intersection
        return len(intersection) / min(len(words1), len(words2))
    
    def _is_generic_content(self, text: str) -> bool:
        """Détecte le contenu trop générique"""
        generic_phrases = [
            "lorem ipsum",
            "test test",
            "aaa",
            "xxx",
            "123456",
            "je participe",
            "i want to win",
            "vote for me",
            "votez pour moi",
            "please vote",
            "s'il vous plaît",
        ]
        
        text_lower = text.lower()
        for phrase in generic_phrases:
            if phrase in text_lower:
                return True
        
        # Vérifier les répétitions excessives
        words = text.split()
        if len(words) > 3:
            unique_words = set(words)
            if len(unique_words) / len(words) < 0.3:
                return True
        
        return False
    
    def _contains_suspicious_links(self, text: str) -> bool:
        """Détecte les liens suspects"""
        # Patterns de liens
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, text)
        
        # Domaines autorisés
        allowed_domains = ["youtube.com", "instagram.com", "tiktok.com", "twitter.com", 
                          "facebook.com", "linkedin.com", "myhigh5.com"]
        
        for url in urls:
            is_allowed = any(domain in url.lower() for domain in allowed_domains)
            if not is_allowed:
                return True
        
        return False
    
    def _check_coherence(self, title: str, description: str) -> float:
        """Vérifie la cohérence entre le titre et la description"""
        title_words = set(re.findall(r'\b\w{3,}\b', title.lower()))
        desc_words = set(re.findall(r'\b\w{3,}\b', description.lower()))
        
        if not title_words:
            return 0.5
        
        # Vérifier si des mots du titre apparaissent dans la description
        overlap = title_words & desc_words
        
        return min(1.0, len(overlap) / len(title_words))
    
    def check_relevance_with_ai(
        self,
        contestant_title: str,
        contestant_description: str,
        contest_title: str,
        contest_description: Optional[str] = None
    ) -> RelevanceResult:
        """
        Vérifie la pertinence avec une IA (OpenAI)
        Fallback sur la méthode basique si pas de clé API
        """
        if not self.openai_api_key:
            return self.check_relevance(
                contestant_title, 
                contestant_description,
                contest_title,
                contest_description
            )
        
        try:
            import json as json_module
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": """Tu es un assistant qui vérifie si une candidature est pertinente pour un concours.
Analyse le titre et la description de la candidature par rapport au concours.
Réponds UNIQUEMENT en JSON avec ce format:
{
  "is_relevant": true/false,
  "score": 0.0-1.0,
  "reasons": ["raison1", "raison2"],
  "suggestions": ["suggestion1", "suggestion2"]
}"""
                        },
                        {
                            "role": "user",
                            "content": f"""Concours: {contest_title}
Description du concours: {contest_description or 'Non spécifiée'}

Candidature - Titre: {contestant_title}
Candidature - Description: {contestant_description}

La candidature est-elle pertinente pour ce concours?"""
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                result_data = json_module.loads(content)
                
                score = float(result_data.get("score", 0.5))
                
                if score >= 0.7:
                    level = RelevanceLevel.HIGH
                elif score >= 0.4:
                    level = RelevanceLevel.MEDIUM
                elif score >= 0.2:
                    level = RelevanceLevel.LOW
                else:
                    level = RelevanceLevel.NONE
                
                return RelevanceResult(
                    is_relevant=result_data.get("is_relevant", score >= RELEVANCE_THRESHOLD),
                    score=score,
                    level=level,
                    reasons=result_data.get("reasons", []),
                    suggestions=result_data.get("suggestions", [])
                )
                    
        except Exception as e:
            logger.error(f"AI relevance check error: {e}")
        
        # Fallback sur la méthode basique
        return self.check_relevance(
            contestant_title, 
            contestant_description,
            contest_title,
            contest_description
        )


# Instance globale du service
content_relevance_service = ContentRelevanceService()
