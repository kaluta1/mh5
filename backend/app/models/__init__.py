# Import all models to ensure they are registered with SQLAlchemy
from .user import User, Role
from .transaction import UserTransaction, Wallet
from .kyc import KYCVerification, KYCDocument, KYCAuditLog
from .voting import Vote, VoteSession, MyFavorites, ContestComment, ContestLike, PageView, ContestantReaction, ContestantShare, ReactionType
from .geography import Continent, Region, Country, City
from .dsp import DSPWallet, DSPTransaction, DSPExchangeRate, DigitalProduct, DigitalPurchase, ProductReview
from .contests import ContestType, ContestCategory, ContestSeason, ContestStage, Contestant, ContestSubmission, ContestantRanking
from .clubs import FanClub, ClubAdmin, ClubMembership, ClubWallet, ClubTransaction, TransactionApproval, ClubContent, ClubContentComment, ClubContentLike
from .affiliate import AffiliateTree, CommissionRate, AffiliateCommission, ReferralLink, ReferralClick, FoundingMember, RevenueShare
from .advertising import AdCampaign, AdCreative, AdPlacement, AdImpression, AdClick, AdRevenueShare, AdBudgetTransaction, AdPerformanceMetrics
from .accounting import ChartOfAccounts, JournalEntry, JournalLine, FinancialReport, RevenueTransaction, TaxConfiguration, AuditTrail
from .media import Media
from .contest import Contest, ContestTemplate, Location, ContestEntry, ContestVote
from .prize import Prize, PrizeWinner, Commission
from .comment import Comment, Like, Report
from .follow import Follow, Affiliation, ReferralCode
from .search_history import SearchHistory
from .notification import Notification, NotificationType

__all__ = [
    "User", "Role", "UserTransaction", "Wallet",
    "KYCVerification", "KYCDocument", "KYCAuditLog",
    "Vote", "VoteSession", "MyFavorites", "ContestComment", "ContestLike", "PageView", "ContestantReaction", "ContestantShare", "ReactionType",
    "Continent", "Region", "Country", "City",
    "DSPWallet", "DSPTransaction", "DSPExchangeRate", "DigitalProduct", "DigitalPurchase", "ProductReview",
    "ContestType", "ContestCategory", "ContestSeason", "ContestStage", "Contestant", "ContestSubmission", "ContestantRanking", "ContestantSeason", "ContestSeasonLink",
    "FanClub", "ClubAdmin", "ClubMembership", "ClubWallet", "ClubTransaction", "TransactionApproval", "ClubContent", "ClubContentComment", "ClubContentLike",
    "AffiliateTree", "CommissionRate", "AffiliateCommission", "ReferralLink", "ReferralClick", "FoundingMember", "RevenueShare",
    "AdCampaign", "AdCreative", "AdPlacement", "AdImpression", "AdClick", "AdRevenueShare", "AdBudgetTransaction", "AdPerformanceMetrics",
    "ChartOfAccounts", "JournalEntry", "JournalLine", "FinancialReport", "RevenueTransaction", "TaxConfiguration", "AuditTrail",
    "Media", "Contest", "ContestTemplate", "Location", "ContestEntry", "ContestVote",
    "Prize", "PrizeWinner", "Commission",
    "Comment", "Like", "Report",
    "Follow", "Affiliation", "ReferralCode",
    "SearchHistory",
    "Notification", "NotificationType",
]
