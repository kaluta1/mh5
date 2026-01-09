"""
Exemple d'implémentation pour le service des agences
Montre comment valider les tokens JWT émis par le service d'authentification
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import httpx

from app.core.security import validate_access_token, get_user_id_from_token
from app.core.config import settings

router = APIRouter()

# Option 1: Valider le token localement (nécessite la même SECRET_KEY)
def get_current_user_from_token(
    authorization: Optional[str] = Header(None)
) -> int:
    """
    Valide le token JWT et retourne l'ID utilisateur.
    IMPORTANT: Le service des agences doit utiliser la même SECRET_KEY que le service d'authentification.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id_from_token(token)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user_id


# Option 2: Valider le token via l'API d'authentification (recommandé pour microservices)
async def validate_token_via_api(
    authorization: Optional[str] = Header(None)
) -> int:
    """
    Valide le token en appelant le service d'authentification.
    Cette approche ne nécessite pas la même SECRET_KEY.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = authorization.replace("Bearer ", "")
    
    # Appeler l'endpoint de validation du service d'authentification
    auth_service_url = settings.FRONTEND_URL.replace(":3000", ":8000")  # Ajuster selon votre configuration
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{auth_service_url}/api/v1/auth/validate-token",
                params={"token": token},
                timeout=5.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token invalide",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            data = response.json()
            return data["user_id"]
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service d'authentification indisponible"
        )


# Exemple d'utilisation dans un endpoint
@router.get("/agences/me")
async def get_my_agency(
    user_id: int = Depends(get_current_user_from_token)  # Option 1
    # user_id: int = Depends(validate_token_via_api)  # Option 2
):
    """
    Récupère les informations de l'agence de l'utilisateur connecté.
    """
    # Utiliser user_id pour récupérer les données de l'agence
    # ...
    return {"user_id": user_id, "message": "Agence récupérée avec succès"}


"""
INSTRUCTIONS POUR LE SERVICE DES AGENCES:

1. IMPORTANT: Assurez-vous que le service des agences utilise la même SECRET_KEY
   que le service d'authentification via la variable d'environnement SECRET_KEY.

2. Si vous ne pouvez pas partager la SECRET_KEY, utilisez l'Option 2 qui appelle
   l'endpoint /api/v1/auth/validate-token du service d'authentification.

3. Pour utiliser l'Option 1 (validation locale):
   - Copiez les fonctions validate_access_token et get_user_id_from_token
     depuis app.core.security
   - Assurez-vous que SECRET_KEY est identique dans les deux services

4. Pour utiliser l'Option 2 (validation via API):
   - Le service des agences doit pouvoir accéder au service d'authentification
   - Utilisez l'endpoint POST /api/v1/auth/validate-token?token=<token>
   - Cette approche est plus lente mais plus flexible
"""
