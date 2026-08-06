from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

try:
    from app.api.api_v1.endpoints import auth, users, media, contests, votes, kyc, contestant, geography, favorites, search, search_history, comments, admin, season_migration, notifications, analytics, affiliate, payments, payment_webhooks, roles, verifications, wallet, suggested_contests, social, private_messages, contact, categories, newsletter, share, follow, rounds, voting_types, fmr, sponsor_annualads, scheduler, referral_shortener
    from app.api.api_v1.endpoints import feed_groups, feed_messages, feed_posts, feed, feed_keys, groups
    logger.info("All endpoints imported successfully")
except ImportError as e:
    logger.error(f"Error importing endpoints: {e}", exc_info=True)
    raise

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentification"])
api_router.include_router(users.router, prefix="/users", tags=["Utilisateurs"])
api_router.include_router(media.router, prefix="/media", tags=["Médias"])
api_router.include_router(contests.router, prefix="/contests", tags=["Concours"])
api_router.include_router(rounds.router, prefix="/rounds", tags=["Rounds"])

# Enregistrer le router categories avec logging
try:
    from app.api.api_v1.endpoints import auth, users, media, contests, votes, kyc, contestant, geography, favorites, search, search_history, comments, admin, season_migration, notifications, analytics, affiliate, payments, roles, verifications, wallet, suggested_contests, social, private_messages, contact, categories, newsletter, share, follow, rounds
    api_router.include_router(categories.router, prefix="/categories", tags=["Catégories"])
    logger.info("Categories router registered successfully at /categories")
except Exception as e:
    logger.error(f"Error registering categories router: {e}", exc_info=True)
    raise
api_router.include_router(suggested_contests.router, prefix="/suggested-contests", tags=["Suggestions de concours"])
api_router.include_router(votes.router, prefix="/votes", tags=["Votes"])
api_router.include_router(voting_types.router, prefix="/voting-types", tags=["Voting Types"])
api_router.include_router(kyc.router, prefix="/kyc", tags=["Vérification KYC"])
api_router.include_router(verifications.router, prefix="/verifications", tags=["Vérifications utilisateur"])
api_router.include_router(payments.router, prefix="/payments", tags=["Paiements"])
api_router.include_router(contestant.router, prefix="/contestants", tags=["Candidatures"])
api_router.include_router(comments.router, prefix="/comments", tags=["Commentaires"])
api_router.include_router(geography.router, prefix="/geography", tags=["Géographie"])
api_router.include_router(favorites.router, prefix="/favorites", tags=["Favoris"])
api_router.include_router(search.router, tags=["Recherche"])
api_router.include_router(search_history.router, tags=["Historique de recherche"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administration"])
api_router.include_router(season_migration.router, prefix="/seasons", tags=["Migrations de saisons"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(affiliate.router, prefix="/affiliates", tags=["Affiliation"])
api_router.include_router(fmr.router, prefix="/fmr", tags=["Founding membership"])
api_router.include_router(sponsor_annualads.webhook_router, prefix="/webhooks", tags=["Webhooks — Annual Ads"])
api_router.include_router(payment_webhooks.router, prefix="/webhooks", tags=["Webhooks — Payments"])
api_router.include_router(sponsor_annualads.sso_router, prefix="/sponsor-embed", tags=["Sponsor embed — Annual Ads"])
api_router.include_router(wallet.router, prefix="/wallet", tags=["Portefeuille"])
api_router.include_router(roles.router, prefix="/rbac", tags=["Rôles et Permissions"])
api_router.include_router(social.router, prefix="/social", tags=["Service Social"])
# Groups router routes already start with /groups/..., so no extra prefix is needed.
# Using an empty prefix keeps the full path as /api/v1/groups/... (api_router is mounted at /api/v1).
api_router.include_router(groups.router, prefix="", tags=["Groupes WhatsApp-like"])
api_router.include_router(private_messages.router, prefix="/messages", tags=["Messagerie Privée"])
api_router.include_router(contact.router, tags=["Contact"])
api_router.include_router(newsletter.router, prefix="/newsletter", tags=["Newsletter"])
api_router.include_router(share.router, prefix="/share", tags=["Partage Social"])
api_router.include_router(referral_shortener.router, tags=["Referral Short Links"])
api_router.include_router(follow.router, prefix="/follow", tags=["Follow"])
api_router.include_router(scheduler.router, prefix="/scheduler", tags=["Scheduler"])

from app.core.build_info import BACKEND_BUILD_ID


@api_router.get("/build-info", tags=["Status"])
def build_info():
    """Confirm deployed backend version (works through nginx /api/v1 proxy)."""
    import os

    return {
        "build_id": BACKEND_BUILD_ID,
        "git_sha": os.getenv("GIT_SHA", BACKEND_BUILD_ID),
        "nomination_roster_fix": True,
    }


@api_router.get("/health/db-schema", tags=["Status"])
def health_db_schema():
    """Report missing users columns (helps debug login 503). No secrets."""
    from sqlalchemy import inspect, text
    from app.db.session import engine
    from app.models.user import User

    try:
        insp = inspect(engine)
        db_cols = {c["name"] for c in insp.get_columns("users")} if insp.has_table("users") else set()
        model_cols = {c.key for c in User.__table__.columns}
        missing = sorted(model_cols - db_cols)
        with engine.connect() as conn:
            who = conn.execute(text("SELECT current_user, current_database()")).fetchone()
        return {
            "ok": len(missing) == 0,
            "db_user": who[0] if who else None,
            "db_name": who[1] if who else None,
            "missing_users_columns": missing,
            "hint": "Run backend/scripts/neon_manual_migrations.sql in Neon SQL Editor" if missing else None,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}

# TEMPORARY: Debug endpoint for continental issue — remove after fix verified
try:
    from app.api.api_v1.endpoints import debug_continental
    api_router.include_router(debug_continental.router, prefix="/debug", tags=["Debug"])
except Exception:
    pass

# Feed System Endpoints (merged from microservice)
api_router.include_router(feed_groups.router, prefix="/feed/groups", tags=["Feed Groups"])
api_router.include_router(feed_messages.router, prefix="/feed/messages", tags=["Feed Messages"])
api_router.include_router(feed_posts.router, prefix="/feed/posts", tags=["Feed Posts"])
api_router.include_router(feed.router, prefix="/feed", tags=["Feed"])
api_router.include_router(feed_keys.router, prefix="/feed/keys", tags=["Feed Encryption Keys"])
