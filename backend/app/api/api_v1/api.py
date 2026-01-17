from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

try:
    from app.api.api_v1.endpoints import auth, users, media, contests, votes, kyc, contestant, geography, favorites, search, search_history, comments, admin, season_migration, notifications, analytics, affiliate, payments, roles, verifications, wallet, voting_types, suggested_contests, social, private_messages, contact, categories, newsletter, share, follow
    from app.api.api_v1.endpoints import feed_groups, feed_messages, feed_posts, feed, feed_keys
    logger.info("All endpoints imported successfully")
except ImportError as e:
    logger.error(f"Error importing endpoints: {e}", exc_info=True)
    raise

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentification"])
api_router.include_router(users.router, prefix="/users", tags=["Utilisateurs"])
api_router.include_router(media.router, prefix="/media", tags=["Médias"])
api_router.include_router(contests.router, prefix="/contests", tags=["Concours"])

# Enregistrer le router categories avec logging
try:
    api_router.include_router(categories.router, prefix="/categories", tags=["Catégories"])
    logger.info("Categories router registered successfully at /categories")
except Exception as e:
    logger.error(f"Error registering categories router: {e}", exc_info=True)
    raise
# IMPORTANT: voting-types doit être inclus AVANT votes pour éviter les conflits de routes
api_router.include_router(voting_types.router, prefix="/voting-types", tags=["Types de vote"])
api_router.include_router(suggested_contests.router, prefix="/suggested-contests", tags=["Suggestions de concours"])
api_router.include_router(votes.router, prefix="/votes", tags=["Votes"])
api_router.include_router(kyc.router, prefix="/kyc", tags=["Vérification KYC"])
api_router.include_router(verifications.router, prefix="/verifications", tags=["Vérifications utilisateur"])
api_router.include_router(payments.router, prefix="/payments", tags=["Paiements"])
api_router.include_router(contestant.router, prefix="/contestants", tags=["Candidatures"])
api_router.include_router(comments.router, prefix="/contestants", tags=["Commentaires"])
api_router.include_router(geography.router, prefix="/geography", tags=["Géographie"])
api_router.include_router(favorites.router, prefix="/favorites", tags=["Favoris"])
api_router.include_router(search.router, tags=["Recherche"])
api_router.include_router(search_history.router, tags=["Historique de recherche"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administration"])
api_router.include_router(season_migration.router, prefix="/seasons", tags=["Migrations de saisons"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(affiliate.router, prefix="/affiliates", tags=["Affiliation"])
api_router.include_router(wallet.router, prefix="/wallet", tags=["Portefeuille"])
api_router.include_router(roles.router, prefix="/rbac", tags=["Rôles et Permissions"])
api_router.include_router(social.router, prefix="/social", tags=["Service Social"])
api_router.include_router(private_messages.router, prefix="/messages", tags=["Messagerie Privée"])
api_router.include_router(contact.router, tags=["Contact"])
api_router.include_router(newsletter.router, prefix="/newsletter", tags=["Newsletter"])
api_router.include_router(share.router, prefix="/share", tags=["Partage Social"])
api_router.include_router(follow.router, prefix="/follow", tags=["Follow"])

# Feed System Endpoints (merged from microservice)
api_router.include_router(feed_groups.router, prefix="/feed/groups", tags=["Feed Groups"])
api_router.include_router(feed_messages.router, prefix="/feed/messages", tags=["Feed Messages"])
api_router.include_router(feed_posts.router, prefix="/feed/posts", tags=["Feed Posts"])
api_router.include_router(feed.router, prefix="/feed", tags=["Feed"])
api_router.include_router(feed_keys.router, prefix="/feed/keys", tags=["Feed Encryption Keys"])
