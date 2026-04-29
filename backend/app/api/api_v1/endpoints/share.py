from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from fastapi import Depends
from typing import Optional
import html
from urllib.parse import urlencode

from app.api import deps
from app.crud import contestant as crud_contestant
from app.crud import user as crud_user
from app.models.contests import Contestant
from app.models.user import User
from app.models.post import Post, PostVisibility

router = APIRouter()


def _get_latest_user_contestant(db: Session, user_id: int) -> Optional[Contestant]:
    latest_active_contestant = (
        db.query(Contestant)
        .filter(
            Contestant.user_id == user_id,
            Contestant.is_deleted.is_(False),
            Contestant.is_active.is_(True),
        )
        .order_by(Contestant.registration_date.desc(), Contestant.id.desc())
        .first()
    )

    if latest_active_contestant:
        return latest_active_contestant

    return (
        db.query(Contestant)
        .filter(
            Contestant.user_id == user_id,
            Contestant.is_deleted.is_(False),
        )
        .order_by(Contestant.registration_date.desc(), Contestant.id.desc())
        .first()
    )


# Routes courtes pour masquer l'API (utilisées dans les liens de partage)
@router.get("/c/{contestant_id}", response_class=HTMLResponse)
async def share_contestant_short(
    contestant_id: int,
    ref: Optional[str] = None,
    db: Session = Depends(deps.get_db)
):
    """
    Route courte pour le partage de contestant
    Redirige vers l'endpoint complet avec métadonnées
    """
    return await share_contestant(contestant_id, ref, db)


@router.get("/p/{username}", response_class=HTMLResponse)
async def share_profile_short(
    username: str,
    ref: Optional[str] = None,
    db: Session = Depends(deps.get_db)
):
    """
    Route courte pour le partage de profil
    Redirige vers l'endpoint complet avec métadonnées
    """
    return await share_profile(username, ref, db)


@router.get("/u/{username}")
async def share_username_short(
    username: str,
    ref: Optional[str] = None,
    db: Session = Depends(deps.get_db)
):
    """
    Username-based short link.
    Redirects to the latest active contestant short link for that user
    and preserves the user's referral code automatically.
    """
    user = crud_user.get_by_username(db, username=username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    contestant = _get_latest_user_contestant(db, user.id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune participation trouvée pour cet utilisateur"
        )

    redirect_path = f"/c/{contestant.id}"
    referral_code = ref or user.personal_referral_code
    if referral_code:
        redirect_path = f"{redirect_path}?{urlencode({'ref': referral_code})}"

    return RedirectResponse(url=redirect_path, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/f/{post_id}", response_class=HTMLResponse)
async def share_feed_post(
    post_id: int,
    ref: Optional[str] = None,
    db: Session = Depends(deps.get_db),
):
    """
    Public share page for a feed post with Open Graph tags.
    Adds referral code to the destination URL when available.
    """
    post = (
        db.query(Post)
        .options(joinedload(Post.author), joinedload(Post.media))
        .filter(
            Post.id == post_id,
            Post.is_deleted.is_(False),
            Post.visibility == PostVisibility.PUBLIC,
        )
        .first()
    )

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found"
        )

    referral_code = ref or (post.author.personal_referral_code if post.author else None)

    flutter_url = f"https://myhigh5.com/dashboard/feed/{post_id}"
    if referral_code:
        flutter_url += f"?{urlencode({'ref': referral_code})}"

    author_name = "MyHigh5 user"
    if post.author:
        author_name = html.escape(
            post.author.full_name
            or post.author.username
            or "MyHigh5 user"
        )

    content_text = (post.content or "").strip()
    title = html.escape(f"{author_name} shared a post on MyHigh5")
    description = html.escape(content_text[:200] or "See this post on MyHigh5.")

    image_url = "https://myhigh5.com/icons/Icon-512.png"
    for post_media in post.media or []:
        media = getattr(post_media, "media", None)
        media_url = getattr(media, "url", None)
        media_type = (getattr(media, "media_type", "") or "").lower()
        if media_url and media_type == "image":
            image_url = media_url
            break

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <meta property="og:type" content="article">
    <meta property="og:url" content="{flutter_url}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:image" content="{image_url}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:site_name" content="MyHigh5">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{flutter_url}">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{description}">
    <meta name="twitter:image" content="{image_url}">

    <title>{title}</title>
    <meta http-equiv="refresh" content="0.5; url={flutter_url}">

    <script>
        setTimeout(function() {{
            window.location.href = "{flutter_url}";
        }}, 500);
    </script>
</head>
<body>
    <p>Redirecting to MyHigh5 post...</p>
</body>
</html>"""

    return HTMLResponse(content=html_content)


@router.get("/r/{referral_code}", response_class=HTMLResponse)
@router.get("/r", response_class=HTMLResponse)
async def share_register(
    referral_code: Optional[str] = None
):
    """
    Route courte pour le partage du lien d'inscription
    Génère une page avec métadonnées Open Graph puis redirige vers l'app
    """
    # URL de redirection vers l'app Flutter
    flutter_url = f"https://myhigh5.com/register"
    if referral_code:
        flutter_url += f"/{referral_code}"
    
    # Titre et description
    title = "Rejoignez MyHighFive"
    description = "Participez à des concours, gagnez des prix et rejoignez une communauté passionnée !"
    image_url = "https://myhigh5.com/icons/Icon-512.png"
    
    # Générer le HTML avec métadonnées Open Graph
    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="{flutter_url}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:image" content="{image_url}">
    <meta property="og:image:width" content="512">
    <meta property="og:image:height" content="512">
    <meta property="og:site_name" content="MyHighFive">
    
    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:url" content="{flutter_url}">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{description}">
    <meta name="twitter:image" content="{image_url}">
    
    <title>{title} - MyHighFive</title>
    
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
        <div class="logo">🎉</div>
        <h1>Bienvenue sur MyHighFive !</h1>
        <p>Vous allez être redirigé vers la page d'inscription...</p>
        <div class="spinner"></div>
        <br><br>
        <a href="{flutter_url}">Cliquez ici si vous n'êtes pas redirigé automatiquement</a>
    </div>
</body>
</html>"""
    
    return HTMLResponse(content=html_content)


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
    
    # Récupérer le nom de l'auteur depuis la relation user
    author_name = "Participant"
    if contestant.user:
        if contestant.user.full_name:
            author_name = html.escape(contestant.user.full_name)
        elif contestant.user.username:
            author_name = html.escape(contestant.user.username)
        elif contestant.user.first_name or contestant.user.last_name:
            name_parts = []
            if contestant.user.first_name:
                name_parts.append(contestant.user.first_name)
            if contestant.user.last_name:
                name_parts.append(contestant.user.last_name)
            author_name = html.escape(" ".join(name_parts))
    
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
