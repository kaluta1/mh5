from logging.config import fileConfig
import os
import sys

# Ajouter le répertoire parent au PYTHONPATH pour résoudre les importations
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from sqlalchemy import engine_from_config
from sqlalchemy import pool
import sqlalchemy as _sqlalchemy

# App models use SQLAlchemy 2.0 API (e.g. mapped_column). System/apt Python often ships 1.x.
_parts = _sqlalchemy.__version__.split(".")
_ma, _mi = int(_parts[0]), int(_parts[1])
if (_ma, _mi) < (2, 0):
    raise RuntimeError(
        f"This project requires SQLAlchemy >= 2.0 (found {_sqlalchemy.__version__}). "
        "You are using system Python/apt Alembic (old SQLAlchemy). "
        "From the backend directory: "
        "python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && "
        "python3 -m alembic upgrade head  "
        "— or: chmod +x scripts/migrate.sh && ./scripts/migrate.sh upgrade head"
    )

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from app.db.base_class import Base

# Import updated User model first
from app.models.user import User

# Import contest models
from app.models.contest import Contest, ContestTemplate, Location, ContestEntry, ContestVote, ContestFavorite, ContestantVerification, VotingType, SuggestedContest

# Import all new MyFav models
from app.models.geography import Continent, Region, Country, City
from app.models.contests import (
    ContestType, ContestCategory, ContestSeason, ContestStage, 
    Contestant, ContestSubmission, ContestantRanking, SeasonLevel
)
from app.models.voting import (
    Vote as VoteModel, VoteSession, MyFavorites, ContestComment, 
    ContestLike, PageView, ContestantVoting
)
from app.models.affiliate import (
    AffiliateTree, AffiliateCommission, CommissionRate, ReferralLink,
    ReferralClick, FoundingMember, RevenueShare
)
from app.models.clubs import (
    FanClub, ClubAdmin, ClubMembership, ClubWallet, ClubTransaction,
    ClubContent, ClubContentComment, ClubContentLike, TransactionApproval
)
from app.models.dsp import (
    DSPWallet, DSPTransaction, DSPExchangeRate, DigitalProduct,
    DigitalPurchase, ProductReview
)
from app.models.advertising import (
    AdCampaign, AdCreative, AdPlacement, AdImpression, AdClick,
    AdRevenueShare, AdBudgetTransaction, AdPerformanceMetrics
)
from app.models.accounting import (
    ChartOfAccounts, JournalEntry, JournalLine, FinancialReport,
    RevenueTransaction, TaxConfiguration, AuditTrail
)
from app.models.founding_pool import FoundingPoolSnapshot, FoundingPoolSnapshotLine
from app.models.contact_message import ContactMessage
from app.models.social_group import (
    SocialGroup, GroupMember, GroupJoinRequest, GroupMessage, 
    MessageReadReceipt, GroupType, GroupMemberRole, MessageType, MessageStatus
)
from app.models.private_message import GroupInvitation

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    from app.core.config import settings
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    from app.core.config import settings
    
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
