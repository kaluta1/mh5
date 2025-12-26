"""
Configuration Socket.IO pour l'application FastAPI
"""
try:
    from socketio import AsyncServer, ASGIApp
    from socketio.exceptions import ConnectionRefusedError
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    AsyncServer = None
    ASGIApp = None

from app.services.social_socket import social_socket_service


def create_socketio_app(fastapi_app):
    """
    Crée et configure l'application Socket.IO
    Retourne None si Socket.IO n'est pas disponible
    """
    if not SOCKETIO_AVAILABLE:
        print("⚠️  Socket.IO n'est pas installé. Les fonctionnalités temps réel seront désactivées.")
        print("   Pour l'installer: pip install python-socketio")
        return None
    
    # Créer le serveur Socket.IO
    sio = AsyncServer(
        cors_allowed_origins="*",
        async_mode='asgi',
        logger=True,
        engineio_logger=False
    )
    
    # Initialiser le service social
    social_socket_service.initialize(sio)
    
    # Créer l'application ASGI pour Socket.IO
    socketio_app = ASGIApp(sio, other_asgi_app=fastapi_app)
    
    return socketio_app

