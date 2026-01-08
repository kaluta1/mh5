from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from fastapi import Depends
from typing import Optional
import html

from app.api import deps
from app.crud import contestant as crud_contestant
from app.crud import user as crud_user
from app.models.contests import Contestant
from app.models.user import User

router = APIRouter()


@router.get("/contestant/{contestant_id}", response_class=HTMLResponse)
async def share_contestant(
    contestant_id: int,
    ref: Optional[str] = None,
    db: Session = Depends(deps.get_db)
):
    """
    Génère une page HTML avec métadonnées Open Graph pour un contestant
    puis redirige automatiquement vers l'app Flutter
    """
    # Récupérer le contestant
    contestant = crud_contestant.get(db, id=contestant_id)
    
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant non trouvé"
        )
    
    # URL de redirection vers l'app Flutter
    flutter_url = f"https://myhigh5.com/contestants/{contestant_id}"
    if ref:
        flutter_url += f"/{ref}"
    
    # Échapper les caractères HTML pour éviter les injections
    title = html.escape(contestant.title or "MyHighFive")
    description = html.escape(contestant.description or "Découvrez cette participation sur MyHighFive")[:200]
    author_name = html.escape(contestant.author_name or "Participant")
    
    # Récupérer la première image ou utiliser une image par défaut
    image_url = "https://myhigh5.com/icons/Icon-512.png"
    if contestant.image_media_ids:
        try:
            import json
            images = json.loads(contestant.image_media_ids)
            if images and len(images) > 0:
                image_url = images[0]
        except:
            pass
    
    # Générer le HTML avec métadonnées Open Graph et Twitter Cards
    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="article">
    <meta property="og:url" content="{flutter_url}">
    <meta property="og:title" content="{title} - {author_name}">
    <meta property="og:description" content="{description}">
    <meta property="og:image" content="{image_url}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:site_name" content="MyHighFive">
    
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{flutter_url}">
    <meta name="twitter:title" content="{title} - {author_name}">
    <meta name="twitter:description" content="{description}">
    <meta name="twitter:image" content="{image_url}">
    
    <!-- WhatsApp -->
    <meta property="og:image:alt" content="{title}">
    
    <title>{title} - MyHighFive</title>
    
    <!-- Redirection automatique vers l'app Flutter après 0.5 secondes -->
    <meta http-equiv="refresh" content="0.5; url={flutter_url}">
    
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            padding: 20px;
        }}
        .container {{
            max-width: 500px;
        }}
        .logo {{
            width: 80px;
            height: 80px;
            margin: 0 auto 20px;
            background: white;
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 40px;
        }}
        h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}
        p {{
            font-size: 16px;
            opacity: 0.9;
            margin-bottom: 30px;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            margin: 0 auto;
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        a {{
            color: white;
            text-decoration: underline;
            font-size: 14px;
        }}
    </style>
    
    <script>
        // Redirection JavaScript en backup
        setTimeout(function() {{
            window.location.href = "{flutter_url}";
        }}, 500);
    </script>
</head>
<body>
    <div class="container">
        <div class="logo">🏆</div>
        <h1>Redirection vers MyHighFive...</h1>
        <p>Vous allez être redirigé vers la participation de {author_name}</p>
        <div class="spinner"></div>
        <br><br>
        <a href="{flutter_url}">Cliquez ici si vous n'êtes pas redirigé automatiquement</a>
    </div>
</body>
</html>"""
    
    return HTMLResponse(content=html_content)


@router.get("/profile/{username}", response_class=HTMLResponse)
async def share_profile(
    username: str,
    ref: Optional[str] = None,
    db: Session = Depends(deps.get_db)
):
    """
    Génère une page HTML avec métadonnées Open Graph pour un profil utilisateur
    puis redirige automatiquement vers l'app Flutter
    """
    # Récupérer l'utilisateur par username
    user = crud_user.get_by_username(db, username=username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    # URL de redirection vers l'app Flutter
    flutter_url = f"https://myhigh5.com/profile/{username}"
    if ref:
        flutter_url += f"/{ref}"
    
    # Échapper les caractères HTML
    full_name = html.escape(user.full_name or user.username or "Utilisateur")
    username_safe = html.escape(username)
    
    # Image de profil ou image par défaut
    avatar_url = user.avatar_url or "https://myhigh5.com/icons/Icon-512.png"
    
    # Générer le HTML avec métadonnées
    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="profile">
    <meta property="og:url" content="{flutter_url}">
    <meta property="og:title" content="{full_name} (@{username_safe}) - MyHighFive">
    <meta property="og:description" content="Découvrez le profil de {full_name} sur MyHighFive">
    <meta property="og:image" content="{avatar_url}">
    <meta property="og:image:width" content="400">
    <meta property="og:image:height" content="400">
    <meta property="og:site_name" content="MyHighFive">
    
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:url" content="{flutter_url}">
    <meta name="twitter:title" content="{full_name} (@{username_safe})">
    <meta name="twitter:description" content="Découvrez le profil de {full_name} sur MyHighFive">
    <meta name="twitter:image" content="{avatar_url}">
    
    <title>{full_name} - MyHighFive</title>
    
    <!-- Redirection automatique -->
    <meta http-equiv="refresh" content="0.5; url={flutter_url}">
    
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            padding: 20px;
        }}
        .container {{
            max-width: 500px;
        }}
        .logo {{
            width: 80px;
            height: 80px;
            margin: 0 auto 20px;
            background: white;
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 40px;
        }}
        h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}
        p {{
            font-size: 16px;
            opacity: 0.9;
            margin-bottom: 30px;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            margin: 0 auto;
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        a {{
            color: white;
            text-decoration: underline;
            font-size: 14px;
        }}
    </style>
    
    <script>
        setTimeout(function() {{
            window.location.href = "{flutter_url}";
        }}, 500);
    </script>
</head>
<body>
    <div class="container">
        <div class="logo">👤</div>
        <h1>Redirection vers MyHighFive...</h1>
        <p>Vous allez être redirigé vers le profil de {full_name}</p>
        <div class="spinner"></div>
        <br><br>
        <a href="{flutter_url}">Cliquez ici si vous n'êtes pas redirigé automatiquement</a>
    </div>
</body>
</html>"""
    
    return HTMLResponse(content=html_content)
